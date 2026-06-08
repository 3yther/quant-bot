import threading
import time
from datetime import datetime, timezone
from typing import Callable

import pandas as pd

import config
import coingecko
import database as db
import notifier


def _macd_state(df: pd.DataFrame) -> tuple[int, bool]:
    """
    Compute MACD on the given OHLC frame.
    Returns (crossover, is_bullish):
      crossover  +1 = fresh bullish cross, -1 = fresh bearish cross, 0 = none
      is_bullish    = MACD line currently above signal line
    """
    d = df.copy()
    d["ema12"] = d["close"].ewm(span=12, adjust=False).mean()
    d["ema26"] = d["close"].ewm(span=26, adjust=False).mean()
    d["macd"]  = d["ema12"] - d["ema26"]
    d["msig"]  = d["macd"].ewm(span=9, adjust=False).mean()

    mc, sc   = d["macd"].iloc[-1], d["msig"].iloc[-1]
    mp, sp   = d["macd"].iloc[-2], d["msig"].iloc[-2]

    bullish = mc > sc
    if mc > sc and mp <= sp:
        cross = 1
    elif mc < sc and mp >= sp:
        cross = -1
    else:
        cross = 0

    return cross, bullish


class PaperTrader:
    def __init__(self, strategy_name: str, strategy_fn: Callable):
        self.strategy_name   = strategy_name
        self.strategy_fn     = strategy_fn
        self.balance         = config.INITIAL_BALANCE
        self.initial_balance = config.INITIAL_BALANCE
        self.position        = 0.0   # BTC held
        self.entry_price     = 0.0
        self.highest_price   = 0.0   # trailing stop watermark
        self.current_price   = 0.0
        self._trades: list[dict] = []
        self._lock    = threading.Lock()
        self._running = False

        # Daily loss tracking — reset at midnight UTC
        self.daily_pnl    = self._load_today_pnl()
        self.trading_date = datetime.now(timezone.utc).date()
        self.daily_halted = False

        # Kill switch — read persisted state from DB on startup
        self.kill_switch = db.get_kill_switch()

    # ------------------------------------------------------------------ #
    #  Startup helper                                                       #
    # ------------------------------------------------------------------ #

    def _load_today_pnl(self) -> float:
        today = datetime.now(timezone.utc).date().isoformat()
        try:
            trades = db.get_recent_trades(500)
            return sum(
                t["pnl"] for t in trades
                if t["timestamp"][:10] == today
                and t["action"] not in ("BUY",)
            )
        except Exception:
            return 0.0

    # ------------------------------------------------------------------ #
    #  Signal: multi-timeframe MACD                                        #
    # ------------------------------------------------------------------ #

    def _current_signal(self) -> int:
        """
        4H trend + 30-min entry multi-timeframe MACD.
          Buy  when: 4H MACD is bullish AND 30-min MACD just crossed bullish.
          Sell when: 30-min MACD crossed bearish OR 4H trend turned bearish.
        """
        df_trend = coingecko.get_ohlc(config.CG_TREND_DAYS)   # 4h candles
        df_entry = coingecko.get_ohlc(config.CG_ENTRY_DAYS)   # 30-min candles

        _,            trend_bullish = _macd_state(df_trend)
        entry_cross,  _             = _macd_state(df_entry)

        if trend_bullish and entry_cross == 1:
            return 1
        if entry_cross == -1 or not trend_bullish:
            return -1
        return 0

    # ------------------------------------------------------------------ #
    #  Daily state management                                              #
    # ------------------------------------------------------------------ #

    def _check_daily_reset(self):
        today = datetime.now(timezone.utc).date()
        if today != self.trading_date:
            self.trading_date = today
            self.daily_pnl    = 0.0
            self.daily_halted = False
            print(f"  [DAILY] UTC midnight — daily P&L counter reset.")

    def _check_daily_limit(self):
        limit = -(config.MAX_DAILY_LOSS * self.initial_balance)
        if self.daily_pnl <= limit and not self.daily_halted:
            self.daily_halted = True
            print(
                f"  [DAILY] Daily loss limit reached  "
                f"(P&L ${self.daily_pnl:,.2f} ≤ limit ${limit:,.2f}) — halting."
            )

    # ------------------------------------------------------------------ #
    #  Trade execution                                                     #
    # ------------------------------------------------------------------ #

    def _execute_buy(self, price: float):
        spend             = self.balance * config.TRADE_SIZE_PCT
        btc               = spend / price
        self.balance     -= spend
        self.position     = btc
        self.entry_price  = price
        self.highest_price = price  # reset watermark on new entry

        sl = round(price * (1 - config.STOP_LOSS_PCT), 2)
        tp = round(price * (1 + config.TAKE_PROFIT_PCT), 2)

        trade = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol":    config.SYMBOL,
            "action":    "BUY",
            "price":     price,
            "size":      btc,
            "pnl":       0.0,
            "balance":   self.balance,
            "strategy":  self.strategy_name,
        }
        self._trades.append(trade)
        db.log_trade(trade)
        notifier.trade_alert(
            action="BUY", price=price, size=btc,
            pnl=0.0, balance=self.balance,
            strategy=self.strategy_name, sl_price=sl, tp_price=tp,
        )
        print(
            f"  [PAPER] BUY        {btc:.6f} BTC @ ${price:>12,.2f}"
            f"  |  Trail SL ${sl:,.2f}  TP ${tp:,.2f}  |  cash ${self.balance:,.2f}"
        )

    def _close_position(self, price: float, action: str):
        proceeds      = self.position * price
        pnl           = (price - self.entry_price) * self.position
        self.balance += proceeds
        self.daily_pnl += pnl
        sign           = "+" if pnl >= 0 else ""

        trade = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol":    config.SYMBOL,
            "action":    action,
            "price":     price,
            "size":      self.position,
            "pnl":       pnl,
            "balance":   self.balance,
            "strategy":  self.strategy_name,
        }
        self._trades.append(trade)
        db.log_trade(trade)
        notifier.trade_alert(
            action=action, price=price, size=self.position,
            pnl=pnl, balance=self.balance, strategy=self.strategy_name,
        )
        label = f"[{action:<14}]"
        print(
            f"  [PAPER] {label} {self.position:.6f} BTC @ ${price:>12,.2f}"
            f"  |  P&L: {sign}${abs(pnl):,.2f}  |  balance: ${self.balance:,.2f}"
        )
        self.position      = 0.0
        self.entry_price   = 0.0
        self.highest_price = 0.0

    # ------------------------------------------------------------------ #
    #  Main loop                                                           #
    # ------------------------------------------------------------------ #

    def run(self):
        """Blocking trading loop — call from a daemon thread."""
        self._running = True
        print(f"\n  Strategy    : {self.strategy_name}")
        print(f"  Balance     : ${self.balance:,.2f} USDT (paper)")
        print(f"  Signal mode : Multi-Timeframe MACD (4H trend + 30M entry)")
        print(f"  Trail stop  : {config.STOP_LOSS_PCT*100:.0f}% below high watermark")
        print(f"  Take Profit : {config.TAKE_PROFIT_PCT*100:.0f}%  |  Daily limit: {config.MAX_DAILY_LOSS*100:.0f}%")
        print(f"  Interval    : every {config.PAPER_TRADE_INTERVAL}s\n")

        while self._running:
            try:
                price  = coingecko.get_price()

                with self._lock:
                    self.current_price = price

                    # Reset daily counter at UTC midnight
                    self._check_daily_reset()

                    # Reload kill switch from DB (dashboard may have toggled it)
                    self.kill_switch = db.get_kill_switch()

                    # Check daily loss limit
                    self._check_daily_limit()

                    halted = self.kill_switch or self.daily_halted

                    if self.position > 0:
                        # Update trailing stop watermark
                        if price > self.highest_price:
                            self.highest_price = price

                        trail_sl = self.highest_price * (1 - config.STOP_LOSS_PCT)
                        tp_price = self.entry_price   * (1 + config.TAKE_PROFIT_PCT)

                        if price <= trail_sl:
                            self._close_position(price, "TRAILING STOP")
                        elif price >= tp_price:
                            self._close_position(price, "TAKE PROFIT")
                        elif not halted:
                            # Fetch signal only if not halted (saves API calls)
                            pass  # signal checked below outside lock

                    if not halted and self.position == 0:
                        pass  # signal checked below

                # Fetch signal outside the lock (network I/O)
                if not (self.kill_switch or self.daily_halted):
                    signal = self._current_signal()
                    with self._lock:
                        if self.position > 0 and signal == -1:
                            self._close_position(self.current_price, "SELL")
                        elif self.position == 0 and signal == 1:
                            self._execute_buy(self.current_price)

            except Exception as exc:
                print(f"  [PAPER] Error: {exc}")

            time.sleep(config.PAPER_TRADE_INTERVAL)

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------ #
    #  Dashboard data                                                      #
    # ------------------------------------------------------------------ #

    def status(self) -> dict:
        with self._lock:
            upnl   = (self.current_price - self.entry_price) * self.position if self.position else 0.0
            equity = self.balance + self.position * self.current_price
            total_pnl = equity - self.initial_balance

            closed = [t for t in self._trades if t["action"] not in ("BUY",)]
            wins   = [t for t in closed if t["pnl"] > 0]

            trail_sl = round(self.highest_price * (1 - config.STOP_LOSS_PCT), 2) if self.position else 0.0
            tp_price = round(self.entry_price   * (1 + config.TAKE_PROFIT_PCT), 2) if self.position else 0.0

            daily_limit = -(config.MAX_DAILY_LOSS * self.initial_balance)

            halt_reason = ""
            if self.kill_switch:
                halt_reason = "Kill switch"
            elif self.daily_halted:
                halt_reason = "Daily loss limit"

            return {
                "strategy":          self.strategy_name,
                "current_price":     self.current_price,
                "initial_balance":   self.initial_balance,
                "cash_balance":      round(self.balance, 2),
                "position_btc":      round(self.position, 8),
                "entry_price":       round(self.entry_price, 2),
                "unrealized_pnl":    round(upnl, 2),
                "unrealized_pct":    round(upnl / (self.entry_price * self.position) * 100, 3) if self.position else 0.0,
                "equity":            round(equity, 2),
                "total_pnl":         round(total_pnl, 2),
                "total_pnl_pct":     round(total_pnl / self.initial_balance * 100, 4),
                "total_trades":      len(closed),
                "win_rate":          round(len(wins) / len(closed) * 100, 1) if closed else 0.0,
                # Trailing stop
                "stop_loss_price":   trail_sl,
                "highest_price":     round(self.highest_price, 2),
                "take_profit_price": tp_price,
                "stop_loss_pct":     config.STOP_LOSS_PCT * 100,
                "take_profit_pct":   config.TAKE_PROFIT_PCT * 100,
                "trade_size_pct":    config.TRADE_SIZE_PCT * 100,
                # Daily loss
                "daily_pnl":         round(self.daily_pnl, 2),
                "daily_limit":       round(daily_limit, 2),
                "daily_halted":      self.daily_halted,
                # Kill switch
                "kill_switch":       self.kill_switch,
                "halted":            self.kill_switch or self.daily_halted,
                "halt_reason":       halt_reason,
                # Multi-timeframe labels
                "trend_tf":          "4H MACD",
                "entry_tf":          "30M MACD",
            }

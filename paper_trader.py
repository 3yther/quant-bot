import threading
import time
from datetime import datetime
from typing import Callable

import pandas as pd
from pybit.unified_trading import HTTP

import config
import database as db
import notifier


class PaperTrader:
    def __init__(self, strategy_name: str, strategy_fn: Callable):
        self.strategy_name = strategy_name
        self.strategy_fn   = strategy_fn
        self.balance        = config.INITIAL_BALANCE
        self.initial_balance = config.INITIAL_BALANCE
        self.position       = 0.0     # BTC held
        self.entry_price    = 0.0
        self.current_price  = 0.0
        self._trades: list[dict] = []
        self._lock   = threading.Lock()
        self._running = False
        self._session = HTTP(
            testnet=True,
            api_key=config.BYBIT_API_KEY,
            api_secret=config.BYBIT_API_SECRET,
        )

    # ------------------------------------------------------------------ #
    #  Data helpers                                                        #
    # ------------------------------------------------------------------ #

    def _fetch_price(self) -> float:
        resp = self._session.get_tickers(
            category=config.CATEGORY, symbol=config.SYMBOL
        )
        return float(resp["result"]["list"][0]["lastPrice"])

    def _fetch_candles(self, limit: int = 250) -> pd.DataFrame:
        resp = self._session.get_kline(
            category=config.CATEGORY,
            symbol=config.SYMBOL,
            interval=config.KLINE_INTERVAL,
            limit=limit,
        )
        raw = resp["result"]["list"]
        df = pd.DataFrame(
            raw,
            columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"],
        )
        df = df.astype({
            "timestamp": "int64", "open": "float64", "high": "float64",
            "low": "float64", "close": "float64", "volume": "float64",
        })
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.sort_values("datetime", inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df

    def _current_signal(self) -> int:
        df   = self._fetch_candles()
        sigs = self.strategy_fn(df)
        return int(sigs.iloc[-1])

    # ------------------------------------------------------------------ #
    #  Trade execution                                                     #
    # ------------------------------------------------------------------ #

    def _execute_buy(self, price: float):
        spend        = self.balance * config.TRADE_SIZE_PCT
        btc          = spend / price
        self.balance -= spend
        self.position    = btc
        self.entry_price = price

        sl = round(price * (1 - config.STOP_LOSS_PCT), 2)
        tp = round(price * (1 + config.TAKE_PROFIT_PCT), 2)

        trade = {
            "timestamp": datetime.utcnow().isoformat(),
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
            f"  |  SL ${sl:,.2f}  TP ${tp:,.2f}  |  cash ${self.balance:,.2f}"
        )

    def _close_position(self, price: float, action: str):
        """Unified exit — handles SELL, STOP LOSS, TAKE PROFIT."""
        proceeds     = self.position * price
        pnl          = (price - self.entry_price) * self.position
        self.balance += proceeds
        sign          = "+" if pnl >= 0 else ""

        trade = {
            "timestamp": datetime.utcnow().isoformat(),
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
        label = f"[{action:<12}]"
        print(
            f"  [PAPER] {label} {self.position:.6f} BTC @ ${price:>12,.2f}"
            f"  |  P&L: {sign}${abs(pnl):,.2f}  |  balance: ${self.balance:,.2f}"
        )
        self.position    = 0.0
        self.entry_price = 0.0

    # ------------------------------------------------------------------ #
    #  Main loop                                                           #
    # ------------------------------------------------------------------ #

    def run(self):
        """Blocking trading loop — call from a daemon thread."""
        self._running = True
        print(f"\n  Strategy    : {self.strategy_name}")
        print(f"  Balance     : ${self.balance:,.2f} USDT (paper)")
        print(f"  Position sz : {config.TRADE_SIZE_PCT*100:.0f}% of balance per trade")
        print(f"  Stop Loss   : {config.STOP_LOSS_PCT*100:.0f}%  |  Take Profit: {config.TAKE_PROFIT_PCT*100:.0f}%")
        print(f"  Interval    : every {config.PAPER_TRADE_INTERVAL}s\n")

        while self._running:
            try:
                # Network calls outside the lock so the dashboard never waits on them
                price  = self._fetch_price()
                signal = self._current_signal()

                with self._lock:
                    self.current_price = price

                    if self.position > 0:
                        sl_price = self.entry_price * (1 - config.STOP_LOSS_PCT)
                        tp_price = self.entry_price * (1 + config.TAKE_PROFIT_PCT)

                        if price <= sl_price:
                            self._close_position(price, "STOP LOSS")
                        elif price >= tp_price:
                            self._close_position(price, "TAKE PROFIT")
                        elif signal == -1:
                            self._close_position(price, "SELL")
                    elif signal == 1:
                        self._execute_buy(price)

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

            closed = [t for t in self._trades if t["action"] in ("SELL", "STOP LOSS", "TAKE PROFIT")]
            wins   = [t for t in closed if t["pnl"] > 0]

            sl_price = round(self.entry_price * (1 - config.STOP_LOSS_PCT), 2) if self.position else 0.0
            tp_price = round(self.entry_price * (1 + config.TAKE_PROFIT_PCT), 2) if self.position else 0.0

            return {
                "strategy":        self.strategy_name,
                "current_price":   self.current_price,
                "initial_balance": self.initial_balance,
                "cash_balance":    round(self.balance, 2),
                "position_btc":    round(self.position, 8),
                "entry_price":     round(self.entry_price, 2),
                "unrealized_pnl":  round(upnl, 2),
                "unrealized_pct":  round(upnl / (self.entry_price * self.position) * 100, 3) if self.position else 0.0,
                "equity":          round(equity, 2),
                "total_pnl":       round(total_pnl, 2),
                "total_pnl_pct":   round(total_pnl / self.initial_balance * 100, 4),
                "total_trades":    len(closed),
                "win_rate":        round(len(wins) / len(closed) * 100, 1) if closed else 0.0,
                "stop_loss_price":   sl_price,
                "take_profit_price": tp_price,
                "stop_loss_pct":     config.STOP_LOSS_PCT * 100,
                "take_profit_pct":   config.TAKE_PROFIT_PCT * 100,
                "trade_size_pct":    config.TRADE_SIZE_PCT * 100,
            }

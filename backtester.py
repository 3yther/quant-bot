import pandas as pd
import numpy as np
import config
import coingecko
from strategies import STRATEGY_REGISTRY


def fetch_historical_data() -> pd.DataFrame:
    """Pull OHLC data from CoinGecko — 4h candles for CG_BACKTEST_DAYS."""
    print(f"  Fetching {config.CG_BACKTEST_DAYS}-day BTC/USD OHLC from CoinGecko…")
    df = coingecko.get_ohlc(config.CG_BACKTEST_DAYS)
    print(f"  Received {len(df)} candles  ({df['datetime'].iloc[0].date()} → {df['datetime'].iloc[-1].date()})")
    return df


def _run_backtest(
    df: pd.DataFrame,
    signals: pd.Series,
    initial_balance: float = config.INITIAL_BALANCE,
    trade_size_pct: float = config.TRADE_SIZE_PCT,
) -> dict:
    balance = initial_balance
    position = 0.0
    entry_price = 0.0
    trades: list[dict] = []
    equity: list[float] = [initial_balance]

    for i in range(len(df)):
        sig = signals.iloc[i]
        price = df["close"].iloc[i]
        dt = df["datetime"].iloc[i]

        if sig == 1 and position == 0:
            spend = balance * trade_size_pct
            position = spend / price
            balance -= spend
            entry_price = price
            trades.append({"dt": dt, "action": "BUY", "price": price, "pnl": 0.0})

        elif sig == -1 and position > 0:
            proceeds = position * price
            pnl = proceeds - position * entry_price
            balance += proceeds
            trades.append({"dt": dt, "action": "SELL", "price": price, "pnl": pnl})
            position = 0.0
            entry_price = 0.0

        equity.append(balance + position * price)

    # Close open position at last price
    if position > 0:
        final_price = df["close"].iloc[-1]
        pnl = (final_price - entry_price) * position
        balance += position * final_price
        trades.append({"dt": df["datetime"].iloc[-1], "action": "CLOSE", "price": final_price, "pnl": pnl})

    final_equity = balance
    total_return = (final_equity - initial_balance) / initial_balance * 100

    closed = [t for t in trades if t["action"] in ("SELL", "CLOSE")]
    wins = [t for t in closed if t["pnl"] > 0]
    win_rate = len(wins) / len(closed) * 100 if closed else 0.0

    eq_series = pd.Series(equity)
    roll_max = eq_series.cummax()
    drawdown = (eq_series - roll_max) / roll_max * 100
    max_dd = float(drawdown.min())

    eq_ret = eq_series.pct_change().dropna()
    if len(df) > 1:
        interval_ms  = int(df["timestamp"].iloc[1]) - int(df["timestamp"].iloc[0])
        interval_min = interval_ms / (1000 * 60)
        periods_per_year = 365 * 24 * 60 / interval_min
    else:
        periods_per_year = 365
    sharpe = (
        float(eq_ret.mean() / eq_ret.std() * np.sqrt(periods_per_year))
        if eq_ret.std() > 0
        else 0.0
    )

    return {
        "total_return": round(total_return, 4),
        "final_equity": round(final_equity, 2),
        "num_trades": len(closed),
        "win_rate": round(win_rate, 2),
        "max_drawdown": round(max_dd, 4),
        "sharpe_ratio": round(sharpe, 4),
        "trades": trades,
        "equity_curve": [round(e, 2) for e in equity],
    }


def run_all_backtests(df: pd.DataFrame) -> dict[str, dict]:
    results = {}
    for name, fn in STRATEGY_REGISTRY.items():
        print(f"  Backtesting  {name}…")
        sigs = fn(df)
        results[name] = _run_backtest(df, sigs)
    return results


def pick_winner(results: dict[str, dict]) -> str:
    if not results:
        raise ValueError("No backtest results to score.")

    returns = {k: v["total_return"] for k, v in results.items()}
    sharpes = {k: v["sharpe_ratio"] for k, v in results.items()}
    wrates  = {k: v["win_rate"]     for k, v in results.items()}

    def _norm(d: dict) -> dict:
        vals = list(d.values())
        lo, hi = min(vals), max(vals)
        rng = hi - lo or 1.0
        return {k: (v - lo) / rng for k, v in d.items()}

    nr = _norm(returns)
    ns = _norm(sharpes)
    nw = _norm(wrates)

    scores = {k: 0.60 * nr[k] + 0.25 * ns[k] + 0.15 * nw[k] for k in results}
    return max(scores, key=scores.__getitem__)


def print_backtest_summary(results: dict[str, dict], winner: str):
    sep = "─" * 78
    print(f"\n{sep}")
    print(f"  {'STRATEGY':<28}  {'RETURN':>8}  {'TRADES':>6}  {'WIN%':>6}  {'MAX DD':>8}  {'SHARPE':>7}")
    print(sep)
    for name, r in results.items():
        flag = " ◀ WINNER" if name == winner else ""
        print(
            f"  {name:<28}  {r['total_return']:>7.2f}%  {r['num_trades']:>6}  "
            f"{r['win_rate']:>5.1f}%  {r['max_drawdown']:>7.2f}%  {r['sharpe_ratio']:>7.3f}{flag}"
        )
    print(sep)

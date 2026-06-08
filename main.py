"""
Bybit Algorithmic Trading Bot
--------------------------------------
Fetches market data from Bybit live API (api.bybit.com).
Backtests all registered strategies over 90 days of historical data,
runs the winner in paper-trading mode, and serves a live
dashboard at http://localhost:5001. No real orders are placed.
"""

import sys
import signal
import threading
import time

import config
import database as db
import dashboard
from backtester import fetch_historical_data, run_all_backtests, pick_winner, print_backtest_summary
from paper_trader import PaperTrader
from strategies import STRATEGY_REGISTRY


# ------------------------------------------------------------------ #
#  Boot checks                                                         #
# ------------------------------------------------------------------ #

def check_config():
    missing = [k for k in ("BYBIT_API_KEY", "BYBIT_API_SECRET")
               if not getattr(config, k)]
    if missing:
        print(
            "\n[!] Missing credentials in .env:\n"
            + "\n".join(f"    {k}" for k in missing)
            + "\n\n    1. Register at https://testnet.bybit.com\n"
            "    2. Create an API key (testnet)\n"
            "    3. Paste key + secret into .env\n"
        )
        sys.exit(1)


# ------------------------------------------------------------------ #
#  Main                                                                #
# ------------------------------------------------------------------ #

def main():
    print("=" * 60)
    print("  Bybit Algo Trading Bot  (Paper Trading)")
    print("  Market data: api.bybit.com  |  Orders: testnet (paper only)")
    print("  No real funds at risk")
    print("=" * 60)

    # Show every registered strategy so it's obvious what will be backtested
    print(f"\n  Strategies loaded ({len(STRATEGY_REGISTRY)}):")
    for name in STRATEGY_REGISTRY:
        print(f"    ✓  {name}")

    # 1. Validate credentials
    check_config()

    # 2. Initialise database
    print("\n[1/5] Initialising SQLite database…")
    db.init_db()
    print("  OK  trades.db ready")

    # 3. Fetch historical data
    print("\n[2/5] Fetching historical data from Bybit live market data…")
    try:
        df = fetch_historical_data()
    except Exception as e:
        print(f"  [!] Failed to fetch data: {e}")
        sys.exit(1)

    # 4. Backtest all registered strategies
    print(f"\n[3/5] Running backtests ({len(STRATEGY_REGISTRY)} strategies)…")
    results = run_all_backtests(df)
    winner = pick_winner(results)
    print_backtest_summary(results, winner)
    db.save_backtest_results(results, winner)
    print(f"\n  Winner: {winner}")

    # 5. Start dashboard
    print(f"\n[4/5] Starting dashboard at http://localhost:{config.DASHBOARD_PORT} …")
    trader = PaperTrader(
        strategy_name=winner,
        strategy_fn=STRATEGY_REGISTRY[winner],
    )
    dashboard.configure(trader, results, winner)
    dashboard.start_server(config.DASHBOARD_PORT)
    print(f"  Dashboard live at  http://localhost:{config.DASHBOARD_PORT}")

    # 6. Start paper trading loop in background thread
    print(f"\n[5/5] Launching paper trading loop…")
    trading_thread = threading.Thread(target=trader.run, daemon=True)
    trading_thread.start()

    # Graceful shutdown on Ctrl-C
    def _shutdown(sig, frame):
        print("\n\n  Shutting down…")
        trader.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    print("\n  Press Ctrl-C to stop.\n")
    while True:
        time.sleep(30)
        st = trader.status()
        print(
            f"  [{time.strftime('%H:%M:%S')}]  price=${st['current_price']:,.2f}"
            f"  equity=${st['equity']:,.2f}"
            f"  P&L={'+' if st['total_pnl'] >= 0 else ''}{st['total_pnl_pct']:.2f}%"
            f"  pos={'LONG' if st['position_btc'] > 0 else 'FLAT'}"
        )


if __name__ == "__main__":
    main()

import os
from dotenv import load_dotenv

load_dotenv()

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")

# Email alerts (Gmail — use an App Password, not your account password)
EMAIL_ADDRESS  = os.getenv("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")

SYMBOL = "BTCUSDT"
CATEGORY = "linear"
KLINE_INTERVAL = "240"       # kept for period-math only (240 min = 4 h)
# CoinGecko OHLC granularity: days 1-2 → 30 min, days 3-30 → 4 hour, days 31+ → 4 day.
# Using 30 for both so we always get 4-hour candles (~180 rows) — enough for all strategies.
CG_BACKTEST_DAYS = 30        # CoinGecko days param for historical backtest (4h candles)
CG_SIGNAL_DAYS   = 30        # CoinGecko days param for live signal (4h candles)
BACKTEST_DAYS = 90
INITIAL_BALANCE = 10000.0    # Paper trading starting USDT
TRADE_SIZE_PCT = 0.10        # Risk 10% of current balance per trade
STOP_LOSS_PCT  = 0.02        # Close position if down 2% from entry
TAKE_PROFIT_PCT = 0.04       # Close position if up 4% from entry
PAPER_TRADE_INTERVAL = 60    # Seconds between signal checks
DASHBOARD_PORT = 5001
DB_PATH = "trades.db"

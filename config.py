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

# CoinGecko OHLC granularity: days 1-2 → 30 min, days 3-30 → 4 h, days 31+ → 4 day.
CG_BACKTEST_DAYS = 30        # 4h candles for historical backtest (~180 rows)
CG_TREND_DAYS    = 30        # 4h candles for multi-timeframe trend MACD
CG_ENTRY_DAYS    = 2         # 30-min candles for multi-timeframe entry MACD

BACKTEST_DAYS    = 90
INITIAL_BALANCE  = 10000.0   # Paper trading starting USDT
TRADE_SIZE_PCT   = 0.10      # Risk 10% of current balance per trade
STOP_LOSS_PCT    = 0.02      # Trailing stop: 2% below high watermark
TAKE_PROFIT_PCT  = 0.04      # Close position if up 4% from entry
MAX_DAILY_LOSS   = 0.05      # Halt trading if daily P&L < -5% of initial balance

PAPER_TRADE_INTERVAL = 60    # Seconds between signal checks
DASHBOARD_PORT = 5001
DB_PATH = "trades.db"

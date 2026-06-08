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
KLINE_INTERVAL = "240"       # 4-hour candles
BACKTEST_DAYS = 90
INITIAL_BALANCE = 10000.0    # Paper trading starting USDT
TRADE_SIZE_PCT = 0.10        # Risk 10% of current balance per trade
STOP_LOSS_PCT  = 0.03        # Close position if down 3% from entry
TAKE_PROFIT_PCT = 0.06       # Close position if up 6% from entry
PAPER_TRADE_INTERVAL = 60    # Seconds between signal checks
DASHBOARD_PORT = 5001
DB_PATH = "trades.db"

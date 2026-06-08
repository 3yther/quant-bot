# ⚡ Quant Bot

A Python algorithmic trading bot for Bitcoin that backtests multiple strategies, selects the best performer, and runs it in paper-trading mode with a live web dashboard. Uses CoinGecko's free API — no keys required, works from any server IP including Railway.

---

## Features

- **Multi-strategy backtesting** — 4 built-in strategies scored by return, Sharpe ratio, and win rate; best strategy auto-selected on startup
  - MA Crossover (50/200)
  - RSI (40/60)
  - MACD Crossover
  - Bollinger Bands (20 / 1.5σ)
- **Multi-timeframe MACD signals** — 4H trend confirmation + 30-minute entry crossover
- **Trailing stop loss** — 2% below the highest price since entry (not fixed from entry)
- **Take profit** — closes at 4% gain from entry
- **Max daily loss limit** — halts all new trades if daily P&L drops below −5%
- **Kill switch** — one-click trading halt from the dashboard, state persisted in SQLite
- **Email alerts** — Gmail SMTP notifications on every trade (BUY, SELL, STOP, TP)
- **SQLite logging** — every trade stored with timestamp, price, size, P&L, and balance
- **Live dashboard** (port 5001):
  - Bloomberg-style dark UI
  - Real-time equity, P&L, cash, win rate, BTC price, daily P&L
  - Open position card with trailing stop and high watermark
  - Strategy config panel with rule box
  - Backtest results table (winner highlighted, performance bars)
  - Live candlestick chart with Bollinger Bands overlay + MACD panel (auto-refreshes every 60s)
  - **Fullscreen chart** — press **F** or click the ⛶ button; **Esc** to exit
  - **Expandable trade rows** — click any trade to reveal full timestamp, trigger reason, entry vs exit price, P&L %, and duration held
  - Kill switch button + trading-halted banner
  - Bot uptime timer

---

## Tech Stack

| Layer | Library |
|---|---|
| Market data | [CoinGecko free API](https://www.coingecko.com/en/api) (no key) |
| Data processing | pandas, numpy |
| Web dashboard | Flask 3 |
| Database | SQLite (built-in) |
| Email | smtplib / Gmail SMTP |
| Charts | Chart.js 4 + chartjs-chart-financial |
| Deployment | Railway |

---

## Running Locally

### 1. Clone and set up

```bash
git clone https://github.com/3yther/quant-bot.git
cd quant-bot
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy the example and fill in your values:

```bash
cp .env.example .env   # or create .env manually
```

`.env` contents:

```env
BYBIT_API_KEY=your_testnet_api_key_here
BYBIT_API_SECRET=your_testnet_api_secret_here
EMAIL_ADDRESS=your_gmail@gmail.com
EMAIL_PASSWORD=your_16_char_app_password
```

> **Email**: Requires a Gmail [App Password](https://myaccount.google.com/apppasswords) (16-character code), not your regular account password. Enable 2-Step Verification first, then generate the app password.

> **Bybit keys**: Testnet keys only — create them at [testnet.bybit.com](https://testnet.bybit.com). The bot places **no real orders** regardless.

### 3. Run

```bash
.venv/bin/python main.py
```

Open the dashboard at **http://localhost:5001**

The bot will:
1. Fetch 30 days of BTC/USD OHLC from CoinGecko
2. Backtest all 4 strategies and select the winner
3. Start the paper-trading loop (checks signal every 60s)
4. Stream live status to the dashboard

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BYBIT_API_KEY` | Yes | Bybit testnet API key (bot checks it exists but uses CoinGecko for data) |
| `BYBIT_API_SECRET` | Yes | Bybit testnet API secret |
| `EMAIL_ADDRESS` | No | Gmail address for trade alerts |
| `EMAIL_PASSWORD` | No | Gmail App Password (16 chars, not your login password) |

---

## Deploying to Railway

### 1. Push to GitHub

```bash
git remote add origin https://github.com/YOUR_USERNAME/quant-bot.git
git push -u origin main
```

### 2. Create Railway project

1. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
2. Select your `quant-bot` repository
3. Railway auto-detects the `Procfile` and uses it

### 3. Add environment variables

In Railway → your service → **Variables**, add:

```
BYBIT_API_KEY=...
BYBIT_API_SECRET=...
EMAIL_ADDRESS=...
EMAIL_PASSWORD=...
```

### 4. Set the port

Railway assigns a dynamic port via `$PORT`. The Procfile uses `python main.py` which reads `config.DASHBOARD_PORT = 5001`. Railway will proxy its external URL to port 5001 automatically if you expose it.

Alternatively, update `config.py` to read from the environment:
```python
DASHBOARD_PORT = int(os.getenv("PORT", 5001))
```

### 5. Deploy

Railway redeploys automatically on every push to `main`. You can also trigger a manual deploy from the Railway dashboard.

**Dashboard URL**: Found in Railway → your service → **Settings** → **Domains** (e.g. `https://quant-bot-production.up.railway.app`)

---

## Strategy Details

All strategies output `+1` (buy), `-1` (sell), or `0` (hold) signals per candle.

| Strategy | Logic |
|---|---|
| MA Crossover | Golden cross (MA50 > MA200) = buy; death cross = sell |
| RSI | Buy when RSI crosses up through 40; sell when it crosses down through 60 |
| MACD Crossover | Buy on MACD line crossing above signal; sell on cross below |
| Bollinger Bands | Buy when price crosses below lower band (1.5σ); sell above upper band |

The live trading signal uses **multi-timeframe MACD** regardless of which strategy won the backtest — the winner's name is shown in the dashboard for reference.

---

## Project Structure

```
quant-bot/
├── main.py            # Entry point — boots everything
├── config.py          # All constants and env vars
├── coingecko.py       # CoinGecko API client with rate-limit backoff
├── strategies.py      # 4 strategy functions + registry
├── backtester.py      # Historical simulation + winner selection
├── paper_trader.py    # Live paper-trading loop, position management
├── database.py        # SQLite schema + CRUD functions
├── dashboard.py       # Flask app + API routes
├── notifier.py        # Gmail email alerts
├── templates/
│   └── index.html     # Dashboard UI (Chart.js, vanilla JS)
├── requirements.txt
├── Procfile           # Railway: web: python main.py
└── .env               # Secrets (not committed)
```

---

Made by Amir

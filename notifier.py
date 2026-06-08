"""
Email alerts via Gmail SMTP.
Requires an App Password — not your regular Gmail password.
Create one at: myaccount.google.com/apppasswords
"""

import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config

_ICONS = {
    "BUY":         "📈",
    "SELL":        "💰",
    "STOP LOSS":   "🛑",
    "TAKE PROFIT": "🎯",
}


def _send(subject: str, body: str):
    if not config.EMAIL_ADDRESS or not config.EMAIL_PASSWORD:
        return
    msg = MIMEMultipart()
    msg["From"]    = f"Quant Bot <{config.EMAIL_ADDRESS}>"
    msg["To"]      = config.EMAIL_ADDRESS
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as smtp:
            smtp.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
            smtp.send_message(msg)
        print(f"  [EMAIL] ✓  {subject}")
    except Exception as exc:
        print(f"  [EMAIL] ✗  {exc}")


def notify(subject: str, body: str):
    """Fire-and-forget — never blocks the trading loop."""
    threading.Thread(target=_send, args=(subject, body), daemon=True).start()


def trade_alert(
    action: str,
    price: float,
    size: float,
    pnl: float,
    balance: float,
    strategy: str,
    sl_price: float = 0.0,
    tp_price: float = 0.0,
):
    icon = _ICONS.get(action, "🤖")
    sign = "+" if pnl >= 0 else ""
    subject = f"{icon} [{action}]  BTC/USDT @ ${price:,.2f}  (Testnet)"

    lines = [
        "=" * 44,
        f"  {icon}  QUANT BOT — Trade Alert",
        "=" * 44,
        "",
        f"  Action    :  {action}",
        f"  Symbol    :  {config.SYMBOL} (Bybit Testnet)",
        f"  Price     :  ${price:,.2f}",
        f"  Size      :  {size:.6f} BTC",
    ]
    if action != "BUY":
        lines.append(f"  P&L       :  {sign}${abs(pnl):,.2f}")
    if action == "BUY" and sl_price and tp_price:
        lines += [
            f"  Stop Loss :  ${sl_price:,.2f}  (-{config.STOP_LOSS_PCT*100:.0f}%)",
            f"  Take Profit: ${tp_price:,.2f}  (+{config.TAKE_PROFIT_PCT*100:.0f}%)",
        ]
    lines += [
        f"  Balance   :  ${balance:,.2f} USDT",
        f"  Strategy  :  {strategy}",
        "",
        "  All trades are simulated (paper trading).",
        "=" * 44,
    ]
    notify(subject, "\n".join(lines))

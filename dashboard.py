import time as _time
import threading
import datetime

import pandas as pd
from flask import Flask, jsonify, render_template, request

import coingecko
import config
import database as db

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True   # never serve a stale template

# Shared state — set by main.py before the server thread starts
_trader = None
_backtest_results: dict = {}
_winner: str = ""
_start_time: float = 0.0

# Chart data cache — refreshed at most once per 60 seconds
_chart_cache: dict = {"ts": 0.0, "data": {}}


def configure(trader, backtest_results: dict, winner: str):
    global _trader, _backtest_results, _winner, _start_time
    _trader = trader
    _backtest_results = backtest_results
    _winner = winner
    _start_time = _time.time()


# ------------------------------------------------------------------ #
#  Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    if _trader is None:
        return jsonify({"error": "Trader not initialised"}), 503
    data = _trader.status()
    data["uptime_seconds"] = int(_time.time() - _start_time) if _start_time else 0
    return jsonify(data)


@app.route("/api/trades")
def api_trades():
    try:
        return jsonify(db.get_recent_trades(50))
    except Exception:
        return jsonify([])


@app.route("/api/backtest")
def api_backtest():
    rows = []
    for name, r in _backtest_results.items():
        rows.append({
            "strategy":     name,
            "total_return": r["total_return"],
            "final_equity": r["final_equity"],
            "num_trades":   r["num_trades"],
            "win_rate":     r["win_rate"],
            "max_drawdown": r["max_drawdown"],
            "sharpe_ratio": r["sharpe_ratio"],
            "is_winner":    name == _winner,
        })
    return jsonify(rows)


@app.route("/api/kill-switch", methods=["GET", "POST"])
def api_kill_switch():
    if request.method == "POST":
        body   = request.get_json(force=True) or {}
        active = bool(body.get("active", False))
        db.set_kill_switch(active)
        if _trader is not None:
            _trader.kill_switch = active
        return jsonify({"active": active})
    return jsonify({"active": db.get_kill_switch()})


@app.route("/api/chart-data")
def api_chart_data():
    now = _time.time()
    if now - _chart_cache["ts"] < 60 and _chart_cache["data"]:
        return jsonify(_chart_cache["data"])
    try:
        df = coingecko.get_ohlc(config.CG_TREND_DAYS)
        df = df.tail(48).copy().reset_index(drop=True)

        # Bollinger Bands (20/1.5σ)
        df["bb_mid"]   = df["close"].rolling(20).mean()
        bb_std         = df["close"].rolling(20).std(ddof=0)
        df["bb_upper"] = df["bb_mid"] + 1.5 * bb_std
        df["bb_lower"] = df["bb_mid"] - 1.5 * bb_std

        # MACD
        df["ema12"]     = df["close"].ewm(span=12, adjust=False).mean()
        df["ema26"]     = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"]      = df["ema12"] - df["ema26"]
        df["macd_sig"]  = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_sig"]

        def _safe(v):
            return None if pd.isna(v) else round(float(v), 2)

        candles = [
            {"x": int(r["timestamp"]), "o": r["open"], "h": r["high"],
             "l": r["low"], "c": r["close"]}
            for _, r in df.iterrows()
        ]

        def _line(col):
            return [{"x": int(r["timestamp"]), "y": _safe(r[col])}
                    for _, r in df.iterrows()]

        # Trade markers — only those falling within the chart window
        oldest_ts = int(df["timestamp"].iloc[0])
        markers = []
        for t in db.get_recent_trades(30):
            try:
                dt    = datetime.datetime.fromisoformat(t["timestamp"])
                ts_ms = int(dt.timestamp() * 1000)
                if ts_ms >= oldest_ts:
                    markers.append({"x": ts_ms, "y": t["price"], "action": t["action"]})
            except Exception:
                pass

        data = {
            "candles":      candles,
            "bb_upper":     _line("bb_upper"),
            "bb_mid":       _line("bb_mid"),
            "bb_lower":     _line("bb_lower"),
            "macd":         _line("macd"),
            "macd_signal":  _line("macd_sig"),
            "macd_hist":    _line("macd_hist"),
            "trades":       markers,
        }
        _chart_cache["ts"]   = now
        _chart_cache["data"] = data
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def start_server(port: int = 5001):
    """Launch Flask in a daemon thread so it doesn't block main."""
    t = threading.Thread(
        target=lambda: app.run(
            host="0.0.0.0", port=port,
            debug=False, use_reloader=False, threaded=True,
        ),
        daemon=True,
    )
    t.start()
    return t

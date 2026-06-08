import threading
from flask import Flask, jsonify, render_template

import database as db

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True   # never serve a stale template

# Shared state — set by main.py before the server thread starts
_trader = None
_backtest_results: dict = {}
_winner: str = ""


def configure(trader, backtest_results: dict, winner: str):
    global _trader, _backtest_results, _winner
    _trader = trader
    _backtest_results = backtest_results
    _winner = winner


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
    return jsonify(_trader.status())


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
        rows.append(
            {
                "strategy": name,
                "total_return": r["total_return"],
                "final_equity": r["final_equity"],
                "num_trades": r["num_trades"],
                "win_rate": r["win_rate"],
                "max_drawdown": r["max_drawdown"],
                "sharpe_ratio": r["sharpe_ratio"],
                "is_winner": name == _winner,
            }
        )
    return jsonify(rows)


def start_server(port: int = 5001):
    """Launch Flask in a daemon thread so it doesn't block main."""
    t = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    t.start()
    return t

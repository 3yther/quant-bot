import sqlite3
from datetime import datetime
from typing import Any
import config


def _conn():
    return sqlite3.connect(config.DB_PATH, check_same_thread=False)


def init_db():
    """Create tables if they don't exist. Safe to call multiple times."""
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT    NOT NULL,
                symbol    TEXT    NOT NULL,
                action    TEXT    NOT NULL,
                price     REAL    NOT NULL,
                size      REAL    NOT NULL,
                pnl       REAL    NOT NULL DEFAULT 0.0,
                balance   REAL    NOT NULL,
                strategy  TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS backtest_results (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                run_timestamp TEXT NOT NULL,
                strategy      TEXT NOT NULL,
                total_return  REAL,
                final_equity  REAL,
                num_trades    INTEGER,
                win_rate      REAL,
                max_drawdown  REAL,
                sharpe_ratio  REAL,
                is_winner     INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS bot_state (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)


# Ensure tables exist as soon as this module is imported.
init_db()


def log_trade(trade: dict[str, Any]):
    with _conn() as con:
        con.execute(
            """INSERT INTO trades
               (timestamp, symbol, action, price, size, pnl, balance, strategy)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trade["timestamp"], trade["symbol"], trade["action"],
                trade["price"], trade["size"], trade["pnl"],
                trade["balance"], trade["strategy"],
            ),
        )


def save_backtest_results(results: dict, winner: str):
    run_ts = datetime.utcnow().isoformat()
    with _conn() as con:
        for strategy, r in results.items():
            con.execute(
                """INSERT INTO backtest_results
                   (run_timestamp, strategy, total_return, final_equity,
                    num_trades, win_rate, max_drawdown, sharpe_ratio, is_winner)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_ts, strategy, r["total_return"], r["final_equity"],
                    r["num_trades"], r["win_rate"], r["max_drawdown"],
                    r["sharpe_ratio"], 1 if strategy == winner else 0,
                ),
            )


def get_recent_trades(limit: int = 50) -> list[dict]:
    with _conn() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_backtest_results() -> list[dict]:
    with _conn() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM backtest_results ORDER BY run_timestamp DESC LIMIT 20"
        ).fetchall()
    return [dict(r) for r in rows]


def get_kill_switch() -> bool:
    with _conn() as con:
        row = con.execute(
            "SELECT value FROM bot_state WHERE key = 'kill_switch'"
        ).fetchone()
    return row is not None and row[0] == "1"


def set_kill_switch(active: bool):
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO bot_state (key, value) VALUES ('kill_switch', ?)",
            ("1" if active else "0",),
        )

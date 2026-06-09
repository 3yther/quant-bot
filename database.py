"""
Database layer — PostgreSQL when DATABASE_URL is set (Railway), SQLite locally.

PostgreSQL connection is managed through a ThreadedConnectionPool so the
single shared pool handles Flask + trading thread concurrency safely within
Railway's connection limits.

SQLite is kept as a zero-config fallback for local development.
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import config

# ─── Backend detection ─────────────────────────────────────────────────────

_DB_URL = os.getenv("DATABASE_URL", "")
# Railway Postgres gives "postgres://" but psycopg2 requires "postgresql://"
if _DB_URL.startswith("postgres://"):
    _DB_URL = _DB_URL.replace("postgres://", "postgresql://", 1)

USE_PG = bool(_DB_URL)

if USE_PG:
    import psycopg2
    import psycopg2.extras
    import psycopg2.pool
    # min=1 keeps one connection warm; max=10 stays well under Railway's limit
    _pool = psycopg2.pool.ThreadedConnectionPool(1, 10, _DB_URL)


# ─── Connection context manager ────────────────────────────────────────────

@contextmanager
def _conn():
    """Yield a connection, commit on success, rollback on error."""
    if USE_PG:
        conn = _pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            _pool.putconn(conn)
    else:
        conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


# ─── Schema ────────────────────────────────────────────────────────────────

def init_db():
    """Create tables if they don't exist. Safe to call multiple times."""
    with _conn() as conn:
        if USE_PG:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id        SERIAL PRIMARY KEY,
                    timestamp TEXT             NOT NULL,
                    symbol    TEXT             NOT NULL,
                    action    TEXT             NOT NULL,
                    price     DOUBLE PRECISION NOT NULL,
                    size      DOUBLE PRECISION NOT NULL,
                    pnl       DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    balance   DOUBLE PRECISION NOT NULL,
                    strategy  TEXT             NOT NULL DEFAULT ''
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS backtest_results (
                    id            SERIAL PRIMARY KEY,
                    run_timestamp TEXT             NOT NULL,
                    strategy      TEXT             NOT NULL,
                    total_return  DOUBLE PRECISION,
                    final_equity  DOUBLE PRECISION,
                    num_trades    INTEGER,
                    win_rate      DOUBLE PRECISION,
                    max_drawdown  DOUBLE PRECISION,
                    sharpe_ratio  DOUBLE PRECISION,
                    is_winner     INTEGER NOT NULL DEFAULT 0
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_state (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            cur.close()
        else:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS trades (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT    NOT NULL,
                    symbol    TEXT    NOT NULL,
                    action    TEXT    NOT NULL,
                    price     REAL    NOT NULL,
                    size      REAL    NOT NULL,
                    pnl       REAL    NOT NULL DEFAULT 0.0,
                    balance   REAL    NOT NULL,
                    strategy  TEXT    NOT NULL DEFAULT ''
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


# Run on import so tables always exist before any route or thread touches the DB
init_db()


# ─── CRUD ──────────────────────────────────────────────────────────────────

def log_trade(trade: dict[str, Any]):
    with _conn() as conn:
        if USE_PG:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO trades
                   (timestamp, symbol, action, price, size, pnl, balance, strategy)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (trade["timestamp"], trade["symbol"], trade["action"],
                 trade["price"], trade["size"], trade["pnl"],
                 trade["balance"], trade["strategy"]),
            )
            cur.close()
        else:
            conn.execute(
                """INSERT INTO trades
                   (timestamp, symbol, action, price, size, pnl, balance, strategy)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (trade["timestamp"], trade["symbol"], trade["action"],
                 trade["price"], trade["size"], trade["pnl"],
                 trade["balance"], trade["strategy"]),
            )


def save_backtest_results(results: dict, winner: str):
    run_ts = datetime.utcnow().isoformat()
    with _conn() as conn:
        for strategy, r in results.items():
            if USE_PG:
                cur = conn.cursor()
                cur.execute(
                    """INSERT INTO backtest_results
                       (run_timestamp, strategy, total_return, final_equity,
                        num_trades, win_rate, max_drawdown, sharpe_ratio, is_winner)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (run_ts, strategy, r["total_return"], r["final_equity"],
                     r["num_trades"], r["win_rate"], r["max_drawdown"],
                     r["sharpe_ratio"], 1 if strategy == winner else 0),
                )
                cur.close()
            else:
                conn.execute(
                    """INSERT INTO backtest_results
                       (run_timestamp, strategy, total_return, final_equity,
                        num_trades, win_rate, max_drawdown, sharpe_ratio, is_winner)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (run_ts, strategy, r["total_return"], r["final_equity"],
                     r["num_trades"], r["win_rate"], r["max_drawdown"],
                     r["sharpe_ratio"], 1 if strategy == winner else 0),
                )


def get_recent_trades(limit: int = 50) -> list[dict]:
    with _conn() as conn:
        if USE_PG:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM trades ORDER BY timestamp DESC LIMIT %s", (limit,)
            )
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
            return rows
        else:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(
                "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()]


def get_backtest_results() -> list[dict]:
    with _conn() as conn:
        if USE_PG:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM backtest_results ORDER BY run_timestamp DESC LIMIT 20"
            )
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
            return rows
        else:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(
                "SELECT * FROM backtest_results ORDER BY run_timestamp DESC LIMIT 20"
            ).fetchall()]


def get_kill_switch() -> bool:
    with _conn() as conn:
        if USE_PG:
            cur = conn.cursor()
            cur.execute("SELECT value FROM bot_state WHERE key = 'kill_switch'")
            row = cur.fetchone()
            cur.close()
        else:
            row = conn.execute(
                "SELECT value FROM bot_state WHERE key = 'kill_switch'"
            ).fetchone()
    return row is not None and row[0] == "1"


def set_kill_switch(active: bool):
    val = "1" if active else "0"
    with _conn() as conn:
        if USE_PG:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO bot_state (key, value) VALUES ('kill_switch', %s)
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                (val,),
            )
            cur.close()
        else:
            conn.execute(
                "INSERT OR REPLACE INTO bot_state (key, value) VALUES ('kill_switch', ?)",
                (val,),
            )

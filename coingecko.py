"""
Shared CoinGecko API client.
All callers (backtester, paper_trader, dashboard) use this module so
rate-limit backoff is consistent and not duplicated.

CoinGecko OHLC granularity (free tier):
  days 1-2  → 30-minute candles
  days 3-30 → 4-hour candles
  days 31+  → 4-day candles
"""

import time
import pandas as pd
import requests

_BASE        = "https://api.coingecko.com/api/v3"
_MAX_RETRIES = 3
_RETRY_BASE  = 60   # seconds — multiplied by attempt number (60, 120, 180)


def _get(url: str, params: dict) -> requests.Response:
    for attempt in range(1, _MAX_RETRIES + 1):
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 429:
            resp.raise_for_status()
            return resp
        wait = _RETRY_BASE * attempt
        print(f"  [CoinGecko] 429 rate limit — waiting {wait}s (attempt {attempt}/{_MAX_RETRIES})…")
        time.sleep(wait)
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp


def _parse_ohlc(raw: list) -> pd.DataFrame:
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close"])
    df = df.astype({
        "timestamp": "int64", "open": "float64", "high": "float64",
        "low": "float64", "close": "float64",
    })
    df["volume"]   = 0.0
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.sort_values("datetime", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def get_ohlc(days: int) -> pd.DataFrame:
    resp = _get(f"{_BASE}/coins/bitcoin/ohlc", {"vs_currency": "usd", "days": days})
    return _parse_ohlc(resp.json())


def get_price() -> float:
    resp = _get(f"{_BASE}/simple/price", {"ids": "bitcoin", "vs_currencies": "usd"})
    return float(resp.json()["bitcoin"]["usd"])

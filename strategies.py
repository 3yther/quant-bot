import pandas as pd
import numpy as np


def ma_crossover_signals(df: pd.DataFrame) -> pd.Series:
    """
    50-period MA vs 200-period MA crossover.
    Signal +1 on golden cross, -1 on death cross.
    """
    d = df.copy()
    d["ma50"] = d["close"].rolling(50).mean()
    d["ma200"] = d["close"].rolling(200).mean()

    prev_ma50 = d["ma50"].shift(1)
    prev_ma200 = d["ma200"].shift(1)

    signal = pd.Series(0, index=d.index)
    signal[(d["ma50"] > d["ma200"]) & (prev_ma50 <= prev_ma200)] = 1
    signal[(d["ma50"] < d["ma200"]) & (prev_ma50 >= prev_ma200)] = -1

    return signal


def rsi_signals(df: pd.DataFrame, period: int = 14, oversold: float = 40, overbought: float = 60) -> pd.Series:
    """
    RSI mean-reversion: buy when RSI crosses up through oversold,
    sell when it crosses down through overbought.
    """
    d = df.copy()
    delta = d["close"].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    d["rsi"] = 100 - (100 / (1 + rs))

    prev_rsi = d["rsi"].shift(1)

    signal = pd.Series(0, index=d.index)
    signal[(d["rsi"] > oversold) & (prev_rsi <= oversold)] = 1
    signal[(d["rsi"] < overbought) & (prev_rsi >= overbought)] = -1

    return signal


def macd_signals(df: pd.DataFrame, fast: int = 12, slow: int = 26, sig: int = 9) -> pd.Series:
    """
    MACD line vs signal line crossover.
    Signal +1 when MACD crosses above, -1 when it crosses below.
    """
    d = df.copy()
    d["ema_fast"] = d["close"].ewm(span=fast, adjust=False).mean()
    d["ema_slow"] = d["close"].ewm(span=slow, adjust=False).mean()
    d["macd"] = d["ema_fast"] - d["ema_slow"]
    d["macd_sig"] = d["macd"].ewm(span=sig, adjust=False).mean()

    prev_macd = d["macd"].shift(1)
    prev_sig = d["macd_sig"].shift(1)

    signal = pd.Series(0, index=d.index)
    signal[(d["macd"] > d["macd_sig"]) & (prev_macd <= prev_sig)] = 1
    signal[(d["macd"] < d["macd_sig"]) & (prev_macd >= prev_sig)] = -1

    return signal


def bollinger_bands_signals(df: pd.DataFrame, period: int = 20, num_std: float = 1.5) -> pd.Series:
    """
    Bollinger Bands mean-reversion: buy when price crosses below the lower
    band, sell when price crosses above the upper band.
    """
    d = df.copy()
    d["bb_mid"] = d["close"].rolling(period).mean()
    bb_std = d["close"].rolling(period).std(ddof=0)
    d["bb_lower"] = d["bb_mid"] - num_std * bb_std
    d["bb_upper"] = d["bb_mid"] + num_std * bb_std

    prev_close = d["close"].shift(1)
    prev_lower = d["bb_lower"].shift(1)
    prev_upper = d["bb_upper"].shift(1)

    signal = pd.Series(0, index=d.index)
    # Price crosses down through lower band → oversold → buy
    signal[(d["close"] <= d["bb_lower"]) & (prev_close > prev_lower)] = 1
    # Price crosses up through upper band → overbought → sell
    signal[(d["close"] >= d["bb_upper"]) & (prev_close < prev_upper)] = -1

    return signal


STRATEGY_REGISTRY = {
    "MA Crossover (50/200)": ma_crossover_signals,
    "RSI (40/60)": rsi_signals,
    "MACD Crossover": macd_signals,
    "Bollinger Bands (20/1.5σ)": bollinger_bands_signals,
}

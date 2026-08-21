"""Indicator computation.

Turns a bar DataFrame into the latest scalar values the voting engine needs, returned as a
plain dict so the engine has no pandas dependency and is trivial to unit-test.

Indicators are computed directly in pandas/numpy using standard formulas (Wilder's RMA for
RSI/ATR, EMA for MACD, population std for Bollinger). pandas-ta is deliberately avoided
because it is not installable on this Python (see requirements.txt); these functions are a
drop-in equivalent for the seven indicators in CLAUDE.md.
"""

from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import config

ET = ZoneInfo("America/New_York")


def _last(series: pd.Series) -> float:
    """Last non-null value of a series as a float, or NaN if none."""
    s = series.dropna()
    return float(s.iloc[-1]) if len(s) else float("nan")


def _rma(series: pd.Series, length: int) -> pd.Series:
    """Wilder's smoothed moving average (RMA), used by RSI and ATR."""
    return series.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()


def _rsi(close: pd.Series, length: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = _rma(gain, length)
    avg_loss = _rma(loss, length)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd_line(close: pd.Series, fast: int, slow: int) -> pd.Series:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    return ema_fast - ema_slow


def _bb_percent(close: pd.Series, length: int, std: float) -> pd.Series:
    mid = close.rolling(length).mean()
    sd = close.rolling(length).std(ddof=0)
    upper = mid + std * sd
    lower = mid - std * sd
    return (close - lower) / (upper - lower).replace(0, np.nan)


def _atr(df: pd.DataFrame, length: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return _rma(tr, length)


def _session_vwap(df: pd.DataFrame) -> float:
    """Session-anchored VWAP: cumulative only over the current trading day's bars.

    VWAP resets at each 9:30 ET open, so we restrict to the bars sharing the ET calendar
    date of the most recent bar. Without this reset a multi-day window (e.g. the backtest)
    would anchor VWAP to a price from days ago and corrupt the price-vs-VWAP vote.
    """
    ts = pd.to_datetime(df["timestamp"])
    et = ts.dt.tz_localize("UTC").dt.tz_convert(ET) if ts.dt.tz is None else ts.dt.tz_convert(ET)
    session_mask = (et.dt.date == et.dt.date.iloc[-1]).values

    sub = df.loc[session_mask]
    typical = (sub["high"] + sub["low"] + sub["close"]) / 3.0
    cum_vol = sub["volume"].cumsum()
    cum_pv = (typical * sub["volume"]).cumsum()
    vwap = cum_pv / cum_vol.replace(0, np.nan)
    return _last(vwap)


def compute_indicators(df: pd.DataFrame) -> dict:
    """Compute the 7 spec indicators (+ ATR for sizing) and return their latest values.

    Volume ratio is a confirmation modifier and ATR is for stop/target sizing; neither
    casts a directional vote.
    """
    close = df["close"]

    rsi = _last(_rsi(close, config.RSI_LENGTH))
    sma20 = _last(close.rolling(config.SMA_FAST).mean())
    sma50 = _last(close.rolling(config.SMA_SLOW).mean())
    macd = _last(_macd_line(close, config.MACD_FAST, config.MACD_SLOW))
    bb_pct = _last(_bb_percent(close, config.BB_LENGTH, config.BB_STD))
    atr = _last(_atr(df, config.ATR_LENGTH))
    vwap = _session_vwap(df)

    avg_vol = df["volume"].rolling(config.VOLUME_AVG_LENGTH).mean()
    volume_ratio = float(df["volume"].iloc[-1] / _last(avg_vol))

    return {
        "close": _last(close),
        "rsi": rsi,
        "sma20": sma20,
        "sma50": sma50,
        "vwap": vwap,
        "macd": macd,
        "bb_pct": bb_pct,
        "volume_ratio": volume_ratio,
        "atr": atr,
    }

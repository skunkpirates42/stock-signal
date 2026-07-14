"""Synthetic bar generator (offline fallback).

Generates a *seeded synthetic* intraday session of 5-minute bars so the pipeline runs with
no API keys and produces reproducible output. This is the fallback `data.source.get_bars`
uses when Alpaca credentials are absent; the live path is `data.alpaca_rest`.

    synthetic_bars(ticker, n) -> pd.DataFrame[timestamp, open, high, low, close, volume]
"""

import hashlib
from datetime import datetime, timedelta

import numpy as np
import pandas as pd


def _seed_for(ticker: str) -> int:
    """Stable per-ticker seed so each name has its own but reproducible price path.

    Uses hashlib rather than builtin hash(), which is salted per process
    (PYTHONHASHSEED) and would make runs non-reproducible.
    """
    digest = hashlib.md5(ticker.encode()).hexdigest()
    return int(digest[:8], 16)


def synthetic_bars(ticker: str, n: int = 120) -> pd.DataFrame:
    """Return ``n`` seeded synthetic 5-minute bars for ``ticker``.

    A single-session geometric random walk with a mild per-ticker drift, plus volume that
    loosely tracks absolute returns. One session keeps VWAP well-defined (VWAP resets each
    trading day).
    """
    rng = np.random.default_rng(_seed_for(ticker))

    start_price = rng.uniform(80, 400)
    drift = rng.uniform(-0.0004, 0.0004)        # per-bar drift, varies by ticker
    vol = rng.uniform(0.001, 0.004)             # per-bar volatility

    returns = rng.normal(drift, vol, size=n)
    close = start_price * np.exp(np.cumsum(returns))

    # Build OHLC around the close path.
    prev_close = np.concatenate([[start_price], close[:-1]])
    open_ = prev_close
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, vol / 2, size=n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, vol / 2, size=n)))

    base_vol = rng.uniform(5e5, 5e6)
    volume = (base_vol * (1 + 5 * np.abs(returns)) * rng.uniform(0.7, 1.3, size=n)).astype(int)

    # Timestamps: consecutive 5-minute bars ending "now", regular-session cadence.
    end = datetime.utcnow().replace(second=0, microsecond=0)
    timestamps = [end - timedelta(minutes=5 * (n - 1 - i)) for i in range(n)]

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )

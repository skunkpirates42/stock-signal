"""Alpaca REST historical bar fetch (live data path).

Pulls recent 5-minute bars from Alpaca's Market Data API (data.alpaca.markets) using the
free IEX feed. Returns the same DataFrame contract as the synthetic generator so nothing
downstream changes:

    fetch_bars(ticker, n) -> pd.DataFrame[timestamp, open, high, low, close, volume]

Credentials come from ALPACA_API_KEY / ALPACA_SECRET_KEY (legacy key-ID + secret auth;
the SDK sends them as the APCA-API-KEY-ID / APCA-API-SECRET-KEY headers).
"""

import os
from datetime import datetime, timedelta, timezone

import pandas as pd

# 5-min bars per regular session (6.5h). Used to size the lookback window.
_BARS_PER_SESSION = 78


def _client():
    from alpaca.data.historical import StockHistoricalDataClient

    key = os.environ["ALPACA_API_KEY"]
    secret = os.environ["ALPACA_SECRET_KEY"]
    return StockHistoricalDataClient(key, secret)


def fetch_bars(ticker: str, n: int = 120) -> pd.DataFrame:
    """Fetch the most recent ``n`` 5-minute IEX bars for ``ticker``."""
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    # Look back enough calendar days to cover n bars including weekends/holidays.
    sessions_needed = n / _BARS_PER_SESSION
    lookback_days = int(sessions_needed * 1.5) + 5
    start = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    request = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=TimeFrame(5, TimeFrameUnit.Minute),
        start=start,
        feed=DataFeed.IEX,  # free tier; SIP requires a paid subscription
    )
    bars = _client().get_stock_bars(request)

    df = bars.df
    if df is None or df.empty:
        raise RuntimeError(
            f"Alpaca returned no bars for {ticker} (feed=IEX, since {start.date()}). "
            "Check the symbol, that markets have traded recently, and that the keys are "
            "paper keys for data.alpaca.markets."
        )

    # bars.df is multi-indexed by (symbol, timestamp); flatten and normalize columns.
    df = df.reset_index()
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    from data.sessions import in_regular_hours, utc
    cutoff = utc(datetime.now(timezone.utc)) - pd.Timedelta(minutes=5)
    df = df[(pd.to_datetime(df.timestamp, utc=True) <= cutoff) & df.timestamp.map(in_regular_hours)]
    return df.tail(n).reset_index(drop=True)

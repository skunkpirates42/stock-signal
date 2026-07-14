"""Data source dispatcher.

Single public entry point for bar data. Uses live Alpaca data when credentials are present
in the environment, otherwise falls back to the seeded synthetic generator so the pipeline
always runs. Callers just use `get_bars(ticker, n)` and never care which source is active.
"""

import os

from data.sample_data import synthetic_bars


def using_alpaca() -> bool:
    return bool(os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_SECRET_KEY"))


def active_source_name() -> str:
    return "alpaca (IEX, live)" if using_alpaca() else "synthetic (offline fallback)"


def get_bars(ticker: str, n: int = 120):
    """Return the last ``n`` 5-minute bars for ``ticker`` from the active source."""
    if using_alpaca():
        from data.alpaca_rest import fetch_bars  # lazy import: only needs alpaca-py when live

        return fetch_bars(ticker, n)
    return synthetic_bars(ticker, n)

"""Alpaca websocket transport.

Thin wrapper around alpaca-py's live `StockDataStream`. Alpaca streams **1-minute** bars
(there is no native 5-minute stream), so this just delivers each 1-min bar to a callback;
the 5-minute aggregation happens in `live.trader.LiveTrader`.

Also exposes `market_clock()` so the runner can report whether the market is open.
"""

import os


def market_clock():
    """Return Alpaca's market clock (is_open, next_open, next_close, timestamp)."""
    from alpaca.trading.client import TradingClient

    client = TradingClient(
        os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"], paper=True
    )
    return client.get_clock()


class BarStream:
    """Subscribes to 1-minute IEX bars for `symbols` and forwards each to `on_minute_bar`.

    `on_minute_bar(symbol, timestamp, open, high, low, close, volume)` is called for every
    incoming 1-minute bar.
    """

    def __init__(self, symbols, on_minute_bar):
        from alpaca.data.enums import DataFeed
        from alpaca.data.live import StockDataStream

        self._stream = StockDataStream(
            os.environ["ALPACA_API_KEY"],
            os.environ["ALPACA_SECRET_KEY"],
            feed=DataFeed.IEX,  # free tier
        )
        self._cb = on_minute_bar

        async def _handler(bar):
            self._cb(
                bar.symbol, bar.timestamp, bar.open, bar.high, bar.low, bar.close, bar.volume
            )

        self._stream.subscribe_bars(_handler, *symbols)

    def run(self):
        """Block, processing bars until interrupted. Manages its own event loop."""
        self._stream.run()

    def stop(self):
        self._stream.stop()

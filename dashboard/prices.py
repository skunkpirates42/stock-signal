"""Read-only IEX marks for the dashboard; never execution or accounting inputs."""
import math
import os
import threading
import time
from datetime import datetime, timezone

import requests


class PositionPrices:
    """One bounded batch cache per Flask process, including failed requests."""

    def __init__(self):
        self._lock = threading.Lock()
        self._symbols = None
        self._expires = 0
        self._result = None

    def get(self, symbols):
        symbols = tuple(sorted(set(symbols)))
        with self._lock:
            if symbols == self._symbols and time.monotonic() < self._expires:
                return self._result
            result = {"feed": "iex", "market_open": None, "prices": {},
                      "checked_at": datetime.now(timezone.utc).isoformat()}
            key = os.environ.get("ALPACA_API_KEY")
            secret = os.environ.get("ALPACA_SECRET_KEY")
            if symbols and key and secret:
                headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
                try:
                    response = requests.get("https://data.alpaca.markets/v2/stocks/trades/latest",
                        params={"symbols": ",".join(symbols), "feed": "iex"},
                        headers=headers, timeout=3)
                    response.raise_for_status()
                    trades = response.json()["trades"]
                    for symbol in symbols:
                        try:
                            trade = trades[symbol]
                            price = float(trade["p"])
                            stamp = datetime.fromisoformat(trade["t"].replace("Z", "+00:00"))
                            if not math.isfinite(price) or price <= 0 or stamp.tzinfo is None:
                                continue
                            if stamp > datetime.now(timezone.utc):
                                continue
                            result["prices"][symbol] = {"price": price, "timestamp": stamp.astimezone(timezone.utc).isoformat()}
                        except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
                            continue
                except (requests.RequestException, ValueError, KeyError, TypeError):
                    pass  # Do not expose HTTP exceptions, credentials, or provider bodies.
                try:
                    response = requests.get("https://paper-api.alpaca.markets/v2/clock",
                                            headers=headers, timeout=3)
                    response.raise_for_status()
                    is_open = response.json().get("is_open")
                    if isinstance(is_open, bool):
                        result["market_open"] = is_open
                except (requests.RequestException, ValueError, AttributeError):
                    pass
            self._symbols, self._result = symbols, result
            self._expires = time.monotonic() + 5
            return result

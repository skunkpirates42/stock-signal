"""Alpaca paper-execution broker (Approach A: real fills, our bar-driven exits).

Drop-in replacement for `PaperBroker` that submits real market orders to the Alpaca paper
account instead of simulating fills locally. It implements the SAME interface LiveTrader
uses (`has_open`, `open_position`, `close_position`, plus `capital`/`open_positions`), so
the live loop is unchanged — only the fill prices become real and the positions actually
exist in your Alpaca paper account.

Design choices (see the wiring discussion in the project notes):
- Entry uses the REAL market fill price, NOT the signal's bar-close price. Stop/target keep
  the signal's absolute planned levels, so the gap between planned and actual entry shows up
  honestly in realized R:R — which is exactly the metric we're validating.
- Exits are still decided by `trades.tracker.check_exit` on each 5-min bar close (that's what
  keeps live comparable to the backtest). When it fires, we market-close the Alpaca position
  and record the REAL fill as the exit price; the WIN/LOSS outcome stays as our logic decided.
- Capital is Alpaca account equity (the real source of truth), refreshed after each close.

The Alpaca client is injectable (`client=`) so this is unit-testable without a network.
"""

import math
import time

import config

# Alpaca order statuses that mean "this order will never fill" — stop polling.
_TERMINAL_BAD = {"canceled", "rejected", "expired", "done_for_day", "suspended"}


def _status(order) -> str:
    """Normalize an Alpaca order status (enum or str) to a lowercase string."""
    return str(getattr(order.status, "value", order.status)).lower()


def _f(value, default=0.0) -> float:
    """Parse an Alpaca numeric field (often a string, sometimes None) to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class AlpacaBroker:
    def __init__(self, client=None, position_pct: float = None,
                 fill_timeout: float = None, poll_interval: float = None):
        self.position_pct = position_pct if position_pct is not None else config.POSITION_PCT
        self.fill_timeout = fill_timeout if fill_timeout is not None else config.ORDER_FILL_TIMEOUT
        self.poll_interval = poll_interval if poll_interval is not None else config.ORDER_POLL_INTERVAL
        self._client = client if client is not None else self._build_client()
        self.open_positions = {}   # ticker -> position dict (our stop/target bookkeeping)
        self.closed_trades = []
        self.capital = self._equity()

    # --- Alpaca plumbing --------------------------------------------------
    @staticmethod
    def _build_client():
        import os

        from alpaca.trading.client import TradingClient

        return TradingClient(
            os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"], paper=True
        )

    def _equity(self) -> float:
        """Current Alpaca account equity — the base for position sizing and reporting."""
        return _f(self._client.get_account().equity, config.STARTING_CAPITAL)

    def _await_fill(self, order_id):
        """Poll an order until it fills; return the filled order. Raises on timeout/reject."""
        deadline = time.monotonic() + self.fill_timeout
        while True:
            order = self._client.get_order_by_id(order_id)
            status = _status(order)
            if status == "filled":
                return order
            if status in _TERMINAL_BAD:
                raise RuntimeError(f"Alpaca order {order_id} ended {status} (no fill).")
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Alpaca order {order_id} not filled within {self.fill_timeout}s "
                    f"(last status: {status})."
                )
            time.sleep(self.poll_interval)

    def _market_order(self, symbol: str, qty: int, side: str):
        """Submit a market DAY order and return the filled order."""
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY if side == "BUY" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        order = self._client.submit_order(order_data=req)
        return self._await_fill(order.id)

    def alpaca_open_symbols(self) -> set:
        """Symbols the Alpaca account currently holds a position in (for reconciliation)."""
        try:
            return {p.symbol for p in self._client.get_all_positions()}
        except Exception:
            return set()

    # --- interface (mirrors PaperBroker) ----------------------------------
    def has_open(self, ticker: str) -> bool:
        return ticker in self.open_positions

    def open_position(self, signal: dict, entry_bar: int, signal_id: int = None):
        """Submit a market order for an actionable signal; return the position at the REAL fill.

        Returns None if it can't/shouldn't open (already in this ticker, non-actionable, too
        small to afford a share, or the order didn't fill).
        """
        ticker = signal["ticker"]
        if signal["direction"] not in ("LONG", "SHORT"):
            return None
        if self.has_open(ticker):
            return None  # one position per ticker at a time

        # Size off current equity and the signal's price; whole shares (brackets/shorts need it).
        budget = self._equity() * self.position_pct
        shares = math.floor(budget / signal["entry"])
        if shares < 1:
            return None

        side = "BUY" if signal["direction"] == "LONG" else "SELL"  # SELL opens a short when flat
        filled = self._market_order(ticker, shares, side)
        entry = _f(filled.filled_avg_price, signal["entry"])
        filled_qty = int(_f(filled.filled_qty, shares))
        if filled_qty < 1:
            return None

        position = {
            "signal_id": signal_id,
            "ticker": ticker,
            "direction": signal["direction"],
            "entry": round(entry, 4),          # REAL fill, not the bar-close plan
            "stop": signal["stop"],            # planned levels stay absolute
            "target": signal["target"],
            "shares": filled_qty,
            "entry_bar": entry_bar,
            "status": "OPEN",
        }
        self.open_positions[ticker] = position
        return position

    def close_position(self, ticker: str, exit_price: float, outcome: str, exit_bar: int,
                       bars_held: int = None):
        """Market-close the Alpaca position. `outcome` (WIN/LOSS) is ours; the exit PRICE and
        P&L come from the REAL fill (the passed `exit_price` is the theoretical stop/target
        level and is only used as a fallback if the fill price is unavailable)."""
        position = self.open_positions.pop(ticker)

        try:
            order = self._client.close_position(ticker)
            filled = self._await_fill(order.id)
            fill_price = _f(filled.filled_avg_price, exit_price)
        except Exception:
            # Couldn't confirm a real fill — fall back to the theoretical level so the trade
            # still closes in our books rather than getting stuck OPEN.
            fill_price = exit_price

        shares = position["shares"]
        if position["direction"] == "LONG":
            pnl = (fill_price - position["entry"]) * shares
        else:  # SHORT
            pnl = (position["entry"] - fill_price) * shares

        if bars_held is None:
            bars_held = exit_bar - position["entry_bar"]

        trade = {
            **position,
            "exit_price": round(fill_price, 4),
            "outcome": outcome,
            "pnl": round(pnl, 2),
            "exit_bar": exit_bar,
            "bars_held": bars_held,
            "status": "CLOSED",
        }
        self.closed_trades.append(trade)
        self.capital = self._equity()  # refresh from Alpaca after the realized P&L lands
        return trade

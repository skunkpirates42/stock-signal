"""Paper trade execution.

PoC implementation is a *local* fill simulator (`PaperBroker`) so the system runs with no
brokerage account. It holds account capital and open positions in memory and enforces the
rules from CLAUDE.md:

- position size = POSITION_PCT (10%) of current capital per trade
- never open a second position in the same ticker while one is open
- track entry/stop/target/shares/entry_bar, and on close: exit price, outcome, P&L, bars held

The broker is pure (no DB, no network) so it's easy to unit-test. When an Alpaca paper
account exists, `open_position`/`close_position` become thin wrappers around Alpaca order
submission (see `# TODO: alpaca` markers); the bookkeeping stays identical.
"""

import math

import config


class PaperBroker:
    def __init__(self, starting_capital: float = None, position_pct: float = None):
        self.capital = starting_capital if starting_capital is not None else config.STARTING_CAPITAL
        self.position_pct = position_pct if position_pct is not None else config.POSITION_PCT
        self.open_positions = {}   # ticker -> position dict
        self.closed_trades = []    # list of closed trade dicts

    def has_open(self, ticker: str) -> bool:
        return ticker in self.open_positions

    def open_position(self, signal: dict, entry_bar: int, signal_id: int = None):
        """Open a paper position from an actionable signal.

        Returns the position dict, or None if it can't/shouldn't open (already in this
        ticker, non-actionable signal, or position too small to afford one share).
        """
        ticker = signal["ticker"]
        if signal["direction"] not in ("LONG", "SHORT"):
            return None
        if self.has_open(ticker):
            return None  # one position per ticker at a time

        entry = signal["entry"]
        budget = self.capital * self.position_pct
        shares = math.floor(budget / entry)
        if shares < 1:
            return None

        # TODO: alpaca — submit a paper market order here and use the real fill price.
        position = {
            "signal_id": signal_id,
            "ticker": ticker,
            "direction": signal["direction"],
            "entry": entry,
            "stop": signal["stop"],
            "target": signal["target"],
            "shares": shares,
            "entry_bar": entry_bar,
            "status": "OPEN",
        }
        self.open_positions[ticker] = position
        return position

    def close_position(self, ticker: str, exit_price: float, outcome: str, exit_bar: int,
                       bars_held: int = None):
        """Close an open position, realize P&L into capital, and return the trade dict.

        `bars_held` may be passed explicitly (the live loop computes it from bar
        timestamps so it survives restarts); if omitted it's `exit_bar - entry_bar`,
        which is what the integer-indexed backtest uses.
        """
        position = self.open_positions.pop(ticker)
        shares = position["shares"]
        if position["direction"] == "LONG":
            pnl = (exit_price - position["entry"]) * shares
        else:  # SHORT
            pnl = (position["entry"] - exit_price) * shares

        # TODO: alpaca — submit the closing order; use the real fill for exit_price.
        self.capital += pnl

        if bars_held is None:
            bars_held = exit_bar - position["entry_bar"]

        trade = {
            **position,
            "exit_price": round(exit_price, 4),
            "outcome": outcome,
            "pnl": round(pnl, 2),
            "exit_bar": exit_bar,
            "bars_held": bars_held,
            "status": "CLOSED",
        }
        self.closed_trades.append(trade)
        return trade

"""Live trading orchestrator.

Owns the in-memory state of the live loop and turns a stream of 1-minute bars into the same
pipeline the backtest runs:

    1-min bars --aggregate--> 5-min bar --indicators--> signal --> (exit mgmt + entry) --> DB

Responsibilities:
- Aggregate 1-minute bars into 5-minute bars per symbol (a bar is "closed" when the first
  bar of the next 5-minute bucket arrives).
- Maintain a rolling window of recent 5-min bars per symbol (seeded from REST history so
  indicators are valid from the first live bar).
- On each closed 5-min bar (regular hours only): manage any open position (stop/target),
  log the signal, and open a new paper position when actionable and flat.
- Reconstruct open positions and account capital from the DB on startup, so restarts don't
  double-open or lose realized P&L.

Network only happens in `seed()` (REST history); everything else is pure and unit-tested.
"""

from collections import deque
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import pandas as pd

import config
from data.source import get_bars
from db.logger import (
    close_trade,
    init_db,
    load_open_positions,
    log_signal,
    log_trade_open,
    realized_pnl,
)
from signals.engine import generate_signal
from signals.indicators import compute_indicators
from signals.llm_synthesis import synthesize
from signals.regime import classify
from trades.executor import PaperBroker
from trades.tracker import check_exit

ET = ZoneInfo("America/New_York")
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)


def floor_5min(ts: datetime) -> datetime:
    """Start of the 5-minute bucket containing `ts`."""
    return ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)


def in_regular_hours(ts: datetime) -> bool:
    """True if `ts` falls within US equity regular trading hours (9:30–16:00 ET, weekday)."""
    et = ts.astimezone(ET)
    if et.weekday() >= 5:  # Sat/Sun
        return False
    return RTH_OPEN <= et.time() < RTH_CLOSE


class LiveTrader:
    def __init__(self, symbols, db_path: str = None, window_size: int = 120):
        self.symbols = list(symbols)
        self.db_path = db_path
        self.window_size = window_size
        self.windows = {s: deque(maxlen=window_size) for s in self.symbols}
        self.buckets = {s: None for s in self.symbols}   # in-progress 5-min bucket
        self.bar_count = {s: 0 for s in self.symbols}     # closed 5-min bars seen this run
        self.on_event = None  # optional callback(kind, payload) for alerts/printing

        init_db(self.db_path)
        self.broker = self._rebuild_broker()

    # --- startup ----------------------------------------------------------
    def _rebuild_broker(self):
        """Reconstruct the broker and any open positions from the DB.

        The stop/target/signal_id/entry_bar bookkeeping always comes from our DB (Alpaca
        doesn't know our planned levels). Only the capital source differs: the local broker
        derives it from starting capital + realized P&L, while the Alpaca broker reads real
        account equity.
        """
        if config.BROKER == "alpaca":
            from trades.alpaca_broker import AlpacaBroker

            broker = AlpacaBroker()
        else:
            broker = PaperBroker(
                starting_capital=config.STARTING_CAPITAL
                + realized_pnl(self.db_path, source="live")
            )

        for row in load_open_positions(self.db_path):
            broker.open_positions[row["ticker"]] = {
                "signal_id": row["signal_id"],
                "ticker": row["ticker"],
                "direction": row["direction"],
                "entry": row["entry"],
                "stop": row["stop"],
                "target": row["target"],
                "shares": row["shares"],
                "entry_bar": row["entry_bar"],
                "status": "OPEN",
                "db_id": row["id"],
                "entry_ts": datetime.fromisoformat(row["created_at"]),
            }

        # With the Alpaca broker, our DB and the real account can drift (a fill or a manual
        # close outside this loop). Surface any mismatch loudly rather than trading on stale state.
        if config.BROKER == "alpaca":
            self._warn_position_drift(broker)

        return broker

    def _warn_position_drift(self, broker) -> None:
        """Compare our reconstructed open positions against Alpaca's actual positions."""
        ours = set(broker.open_positions)
        theirs = broker.alpaca_open_symbols()
        if ours != theirs:
            print(
                "  WARN broker/DB position mismatch — "
                f"ours={sorted(ours) or '[]'} alpaca={sorted(theirs) or '[]'}. "
                "Reconcile before trading (a fill or close may have happened outside this loop).",
                flush=True,
            )

    def seed(self) -> None:
        """Fill each rolling window with recent 5-min bars from REST history."""
        for s in self.symbols:
            df = get_bars(s, self.window_size)
            self.windows[s] = deque(
                (df[["timestamp", "open", "high", "low", "close", "volume"]]
                 .to_dict("records")),
                maxlen=self.window_size,
            )

    def _emit(self, kind: str, payload) -> None:
        if self.on_event:
            self.on_event(kind, payload)

    # --- aggregation ------------------------------------------------------
    def on_minute_bar(self, symbol, ts, open_, high, low, close, volume):
        """Feed one 1-minute bar. Returns the finalized 5-min bar dict when a bucket closes."""
        start = floor_5min(ts)
        b = self.buckets[symbol]

        if b is None:
            self.buckets[symbol] = self._new_bucket(start, open_, high, low, close, volume)
            return None

        if start != b["start"]:
            finalized = self._finalize(b)
            self.buckets[symbol] = self._new_bucket(start, open_, high, low, close, volume)
            self._on_bar_close(symbol, finalized)
            return finalized

        # Same bucket: extend it.
        b["high"] = max(b["high"], high)
        b["low"] = min(b["low"], low)
        b["close"] = close
        b["volume"] += volume
        return None

    @staticmethod
    def _new_bucket(start, open_, high, low, close, volume):
        return {"start": start, "open": open_, "high": high, "low": low,
                "close": close, "volume": volume}

    @staticmethod
    def _finalize(b) -> dict:
        return {"timestamp": b["start"], "open": b["open"], "high": b["high"],
                "low": b["low"], "close": b["close"], "volume": b["volume"]}

    # --- pipeline on a closed 5-min bar -----------------------------------
    def _on_bar_close(self, symbol, bar5):
        """Run exit management + signal + entry for one closed 5-min bar."""
        if not in_regular_hours(bar5["timestamp"]):
            return None  # market hours only

        self.windows[symbol].append(bar5)
        self.bar_count[symbol] += 1

        # 1) Manage an open position against this bar's range.
        closed_this_bar = False
        if self.broker.has_open(symbol):
            pos = self.broker.open_positions[symbol]
            exit_ = check_exit(pos, bar5)
            if exit_:
                bars_held = self._bars_between(pos.get("entry_ts"), bar5["timestamp"])
                trade = self.broker.close_position(
                    symbol, exit_["exit_price"], exit_["outcome"],
                    exit_bar=self.bar_count[symbol], bars_held=bars_held,
                )
                close_trade(pos["db_id"], trade, self.db_path)
                self._emit("close", trade)
                closed_this_bar = True

        # Need enough history to compute indicators.
        if len(self.windows[symbol]) < config.WARMUP_BARS:
            return None

        # 2) Generate + log the signal (every bar, per CLAUDE.md).
        signal = generate_signal(symbol, compute_indicators(pd.DataFrame(list(self.windows[symbol]))))
        signal["regime"] = self._current_regime()
        # Template only: a bar close must never make a network call. Real LLM reasoning is
        # generated on demand from the dashboard, so we pay per signal actually read
        # rather than per signal produced.
        synthesize(signal, provider="template")
        signal_id = log_signal(signal, bar_timestamp=bar5["timestamp"], db_path=self.db_path)
        self._emit("signal", signal)

        # 3) Open a paper position if actionable, flat, and we didn't just exit this bar.
        if (signal["direction"] in ("LONG", "SHORT")
                and not self.broker.has_open(symbol)
                and not closed_this_bar):
            pos = self.broker.open_position(signal, entry_bar=self.bar_count[symbol], signal_id=signal_id)
            if pos is not None:
                pos["entry_ts"] = bar5["timestamp"]
                pos["db_id"] = log_trade_open(pos, self.db_path)
                self._emit("open", pos)

        return signal

    def _current_regime(self):
        """Classify the market regime from the latest SPY/QQQ windows (None if unavailable)."""
        def latest_ind(sym):
            w = self.windows.get(sym)
            if not w or len(w) < config.WARMUP_BARS:
                return None
            return compute_indicators(pd.DataFrame(list(w)))
        spy = latest_ind("SPY")
        if spy is None:
            return None
        return classify(spy, latest_ind("QQQ"))

    @staticmethod
    def _bars_between(entry_ts, exit_ts) -> int:
        """Number of 5-min bars between two timestamps (restart-safe bars_held)."""
        if entry_ts is None:
            return None
        return max(0, round((exit_ts - entry_ts).total_seconds() / 300))

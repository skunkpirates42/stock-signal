"""Alert feed — turn signal/trade rows into a unified alert-event stream.

The dashboard's "alert conditions" ARE the signal engine's own output: there is no
separate rule engine (see CLAUDE.md — the engine decides, everything downstream just
surfaces it). An "alert" is therefore one of three events:

    signal  — a new actionable LONG/SHORT signal fired
    open    — a paper trade opened
    close   — a paper trade closed (WIN/LOSS + P&L)

`build_alert_events` is a pure function over lists of row dicts (as returned by the DB
layer) so it's trivial to unit-test and is reused by the `/api/alerts` endpoint. Each
event carries a stable `key` (e.g. "sig:123", "open:45", "close:45") the browser uses to
tell new alerts from ones it has already shown/notified.
"""

ACTIONABLE = ("LONG", "SHORT")
CLOSED = ("WIN", "LOSS")


def build_alert_events(signals, trades, limit: int = 80) -> list:
    """Merge recent signals + trades into a newest-first list of alert events.

    Args:
        signals: rows from the `signals` table (dicts).
        trades:  rows from the `trades` table (dicts).
        limit:   max events to return.

    WAIT signals are skipped (nothing to alert on). Each trade yields an `open` event and,
    once closed, a separate `close` event. Ordering is by insertion/close time (`created_at`
    / `closed_at`), which is a single consistent ISO-UTC clock across both tables.
    """
    events = []

    for s in signals:
        if s.get("direction") not in ACTIONABLE:
            continue
        events.append({
            "key": f"sig:{s['id']}",
            "kind": "signal",
            "ticker": s.get("ticker"),
            "direction": s.get("direction"),
            "confidence": s.get("confidence"),
            "entry": s.get("entry"),
            "stop": s.get("stop"),
            "target": s.get("target"),
            "rr": s.get("rr"),
            "regime": s.get("regime"),
            "bar_time": s.get("bar_timestamp"),
            "order_ts": s.get("created_at") or s.get("bar_timestamp") or "",
        })

    for t in trades:
        if t.get("created_at"):
            events.append({
                "key": f"open:{t['id']}",
                "kind": "open",
                "ticker": t.get("ticker"),
                "direction": t.get("direction"),
                "entry": t.get("entry"),
                "shares": t.get("shares"),
                "order_ts": t.get("created_at") or "",
            })
        if t.get("outcome") in CLOSED and t.get("closed_at"):
            events.append({
                "key": f"close:{t['id']}",
                "kind": "close",
                "ticker": t.get("ticker"),
                "direction": t.get("direction"),
                "outcome": t.get("outcome"),
                "pnl": t.get("pnl"),
                "exit": t.get("exit_price"),
                "bars_held": t.get("bars_held"),
                "order_ts": t.get("closed_at") or "",
            })

    events.sort(key=lambda e: e["order_ts"], reverse=True)
    return events[:limit]

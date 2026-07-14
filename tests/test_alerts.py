"""Tests for the alert feed (pure) and desktop notifier (best-effort, mocked)."""

from unittest import mock

from alerts.desktop import format_event, notify, notify_event
from alerts.feed import build_alert_events


# --- feed ------------------------------------------------------------------

def _signal(id, direction="LONG", created="2026-07-14T14:00:00+00:00", conf=0.7):
    return {"id": id, "ticker": "NVDA", "direction": direction, "confidence": conf,
            "entry": 100.0, "stop": 98.0, "target": 104.0, "rr": 2.0,
            "regime": "trending", "bar_timestamp": "2026-07-14 10:00:00", "created_at": created}


def _trade(id, outcome="OPEN", created="2026-07-14T14:00:05+00:00", closed=None):
    return {"id": id, "ticker": "NVDA", "direction": "LONG", "entry": 100.0,
            "stop": 98.0, "target": 104.0, "shares": 50, "exit_price": 104.0 if closed else None,
            "outcome": outcome, "pnl": 200.0 if closed else None, "bars_held": 6 if closed else None,
            "created_at": created, "closed_at": closed}


def test_wait_signals_are_not_alerts():
    events = build_alert_events([_signal(1, "WAIT"), _signal(2, "LONG")], [])
    assert [e["key"] for e in events] == ["sig:2"]


def test_open_and_close_yield_separate_events():
    t = _trade(9, outcome="WIN", closed="2026-07-14T15:00:00+00:00")
    events = build_alert_events([], [t])
    keys = {e["key"] for e in events}
    assert keys == {"open:9", "close:9"}
    close = next(e for e in events if e["kind"] == "close")
    assert close["outcome"] == "WIN" and close["pnl"] == 200.0


def test_open_only_trade_has_no_close_event():
    events = build_alert_events([], [_trade(3, outcome="OPEN")])
    assert [e["key"] for e in events] == ["open:3"]


def test_events_sorted_newest_first_and_capped():
    signals = [_signal(i, created=f"2026-07-14T{10+i:02d}:00:00+00:00") for i in range(5)]
    events = build_alert_events(signals, [], limit=3)
    assert len(events) == 3
    order = [e["order_ts"] for e in events]
    assert order == sorted(order, reverse=True)


# --- desktop notifier ------------------------------------------------------

def test_notify_is_noop_off_macos():
    with mock.patch("alerts.desktop.platform.system", return_value="Linux"):
        assert notify("t", "b") is False


def test_notify_dispatches_on_macos():
    with mock.patch("alerts.desktop.platform.system", return_value="Darwin"), \
         mock.patch("alerts.desktop.subprocess.run") as run:
        assert notify("Title", "Body", subtitle="sub", sound="Ping") is True
        run.assert_called_once()
        args = run.call_args[0][0]
        assert args[0] == "osascript"
        assert "display notification" in args[2]


def test_notify_escapes_quotes():
    with mock.patch("alerts.desktop.platform.system", return_value="Darwin"), \
         mock.patch("alerts.desktop.subprocess.run") as run:
        notify('has "quote"', 'body')
        script = run.call_args[0][0][2]
        assert '\\"quote\\"' in script  # embedded quote is escaped, not left raw


def test_notify_event_skips_wait_and_low_confidence():
    with mock.patch("alerts.desktop.notify") as n:
        assert notify_event("signal", {"ticker": "X", "direction": "WAIT"}) is False
        assert notify_event("signal", {"ticker": "X", "direction": "LONG", "confidence": 0.4},
                            min_confidence=0.6) is False
        n.assert_not_called()


def test_notify_event_fires_for_actionable_signal():
    with mock.patch("alerts.desktop.notify", return_value=True) as n:
        assert notify_event("signal", {"ticker": "X", "direction": "LONG", "confidence": 0.7,
                                        "entry": 1, "stop": 1, "target": 1, "rr": 2},
                            min_confidence=0.6) is True
        n.assert_called_once()


def test_format_event_shapes():
    title, sub, body = format_event("close", {"ticker": "AAPL", "outcome": "WIN",
                                              "pnl": 120.5, "exit_price": 190.0, "bars_held": 4})
    assert title == "AAPL WIN"
    assert "+120.50" in sub
    assert "190.0" in body

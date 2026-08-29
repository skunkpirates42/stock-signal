"""Tests for the live loop's deterministic logic: 5-min aggregation, regular-hours
filtering, and restart reconstruction from the DB. (Signal/exit/entry math is covered by
the engine/executor/tracker tests and the end-to-end backtest.)
"""

import sqlite3
from collections import deque
from datetime import datetime, timedelta, timezone

import config
from signals import llm_synthesis
from db.logger import init_db, log_signal, log_trade_open, close_trade
from live.trader import LiveTrader, floor_5min, in_regular_hours

# A weekday during US regular hours, expressed in UTC (14:30 UTC = 10:30 ET, EDT).
RTH = datetime(2026, 6, 10, 14, 30, tzinfo=timezone.utc)
PREMARKET = datetime(2026, 6, 10, 11, 0, tzinfo=timezone.utc)  # 07:00 ET


def _trader(tmp_path):
    db = str(tmp_path / "t.db")
    return LiveTrader(["AAA"], db_path=db, window_size=50), db


def test_floor_5min():
    assert floor_5min(datetime(2026, 6, 10, 14, 32, 41)) == datetime(2026, 6, 10, 14, 30)
    assert floor_5min(datetime(2026, 6, 10, 14, 35, 0)) == datetime(2026, 6, 10, 14, 35)


def test_regular_hours_filter():
    assert in_regular_hours(RTH) is True
    assert in_regular_hours(PREMARKET) is False
    # Saturday, even at midday ET.
    assert in_regular_hours(datetime(2026, 6, 13, 16, 0, tzinfo=timezone.utc)) is False


def test_aggregation_builds_correct_5min_bar(tmp_path):
    trader, _ = _trader(tmp_path)
    base = RTH
    # Five 1-min bars in the 14:30 bucket; the bucket closes when 14:35 arrives.
    for i, (o, h, l, c, v) in enumerate([
        (10, 11, 9.5, 10.5, 100),
        (10.5, 12, 10.4, 11, 120),
        (11, 11.5, 10.0, 10.2, 90),
        (10.2, 10.8, 9.8, 10.6, 110),
        (10.6, 13, 10.5, 12.5, 130),
    ]):
        assert trader.on_minute_bar("AAA", base.replace(minute=30 + i), o, h, l, c, v) is None
    # First bar of next bucket finalizes the previous one.
    bar5 = trader.on_minute_bar("AAA", base.replace(minute=35), 12.5, 12.6, 12.4, 12.5, 50)
    assert bar5["open"] == 10           # first bar's open
    assert bar5["high"] == 13           # max high
    assert bar5["low"] == 9.5           # min low
    assert bar5["close"] == 12.5        # last bar's close
    assert bar5["volume"] == 550        # summed volume
    assert bar5["timestamp"] == datetime(2026, 6, 10, 14, 30, tzinfo=timezone.utc)


def test_premarket_bar_not_added_to_window(tmp_path):
    trader, _ = _trader(tmp_path)
    # Close a bucket whose timestamp is pre-market; window must stay empty.
    trader.on_minute_bar("AAA", PREMARKET.replace(minute=0), 10, 10, 10, 10, 100)
    trader.on_minute_bar("AAA", PREMARKET.replace(minute=5), 10, 10, 10, 10, 100)
    assert len(trader.windows["AAA"]) == 0


def test_reconstructs_capital_and_open_positions(tmp_path):
    db = str(tmp_path / "r.db")
    init_db(db)
    # One closed winner (+250) and one still-open position.
    sid = log_signal({"ticker": "AAA", "direction": "LONG", "confidence": 0.7, "entry": 100,
                      "stop": 98, "target": 104, "rr": 2.0, "indicators_json": "{}",
                      "reasoning": "x"}, db_path=db)
    win = {"signal_id": sid, "ticker": "AAA", "direction": "LONG", "entry": 100, "stop": 98,
           "target": 104, "shares": 10, "entry_bar": 1}
    tid = log_trade_open(win, db_path=db)
    close_trade(tid, {**win, "exit_price": 104, "outcome": "WIN", "pnl": 250.0,
                      "exit_bar": 6, "bars_held": 5}, db_path=db)

    open_pos = {"signal_id": sid, "ticker": "BBB", "direction": "SHORT", "entry": 50, "stop": 51,
                "target": 48, "shares": 20, "entry_bar": 2}
    log_trade_open(open_pos, db_path=db)

    trader = LiveTrader(["AAA", "BBB"], db_path=db)
    assert trader.broker.capital == config.STARTING_CAPITAL + 250.0
    assert trader.broker.has_open("BBB")
    assert not trader.broker.has_open("AAA")
    assert trader.broker.open_positions["BBB"]["shares"] == 20


def _seed_window(trader, symbol, n=60):
    """Fill a symbol's rolling window with enough varied bars for indicators to compute."""
    base = datetime(2026, 6, 10, 13, 0, tzinfo=timezone.utc)
    for i in range(n):
        close = 100 + (i % 7) - 3
        trader.windows[symbol].append({
            "timestamp": base + timedelta(minutes=5 * i),
            "open": close - 0.5, "high": close + 1.0, "low": close - 1.0,
            "close": close, "volume": 1000 + 10 * (i % 5),
        })


def test_bar_close_never_calls_a_paid_llm_provider(tmp_path, monkeypatch):
    """A bar close must cost nothing: synthesis is pinned to the offline template.

    The distinction that matters is `synthesis_source == "template"` exactly — a fallback
    would read "template (fell back from groq: ...)" and would mean a request was attempted.
    """
    def boom(signal):
        raise AssertionError("live loop must not call a paid provider on bar close")

    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(llm_synthesis, "_groq_reasoning", boom)
    monkeypatch.setattr(llm_synthesis, "_anthropic_reasoning", boom)

    trader, db = _trader(tmp_path)
    trader.windows["AAA"] = deque(trader.windows["AAA"], maxlen=120)
    _seed_window(trader, "AAA")

    bar = {"timestamp": RTH, "open": 100.0, "high": 101.0, "low": 99.0,
           "close": 100.5, "volume": 1500}
    signal = trader._on_bar_close("AAA", bar)

    assert signal is not None, "expected a signal once the window is warm"
    assert signal["synthesis_source"] == "template"
    assert signal["reasoning"]

    conn = sqlite3.connect(db)
    stored = conn.execute(
        "SELECT reasoning, synthesis_source FROM signals ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert stored[1] == "template"
    assert stored[0], "every signal is logged with reasoning, WAIT included"

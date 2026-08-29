"""Tests for the dashboard's API endpoints, exercised via Flask's test client against a
temp DB seeded with one closed + one open trade. No server/browser needed.
"""

import json
import sqlite3

import config
from dashboard.app import create_app
from signals import llm_synthesis
from db.logger import close_trade, init_db, log_signal, log_trade_open


def _seed(db):
    init_db(db)
    sid = log_signal({"ticker": "AAA", "direction": "LONG", "confidence": 0.7, "entry": 100,
                      "stop": 98, "target": 104, "rr": 2.0, "indicators_json": "{}",
                      "reasoning": "x"}, bar_timestamp="2026-06-10T14:30:00", db_path=db)
    win = {"signal_id": sid, "ticker": "AAA", "direction": "LONG", "entry": 100, "stop": 98,
           "target": 104, "shares": 10, "entry_bar": 1}
    tid = log_trade_open(win, db_path=db)
    close_trade(tid, {**win, "exit_price": 104, "outcome": "WIN", "pnl": 40.0,
                      "exit_bar": 6, "bars_held": 5}, db_path=db)
    log_trade_open({"signal_id": sid, "ticker": "BBB", "direction": "SHORT", "entry": 50,
                    "stop": 51, "target": 48, "shares": 20, "entry_bar": 2}, db_path=db)


def _client(tmp_path):
    db = str(tmp_path / "d.db")
    _seed(db)
    return create_app(db_path=db).test_client()


def test_index_serves_html(tmp_path):
    r = _client(tmp_path).get("/")
    assert r.status_code == 200
    assert b"Paper Trader" in r.data


def test_metrics_endpoint(tmp_path):
    m = _client(tmp_path).get("/api/metrics").get_json()
    assert m["n_closed"] == 1
    assert m["n_open"] == 1
    assert m["win_rate"] == 1.0
    assert m["total_pnl"] == 40.0
    # equity curve: start point + one closed trade.
    assert len(m["equity"]) == 2
    assert m["equity"][-1]["equity"] == config.STARTING_CAPITAL + 40.0


def test_metrics_endpoint_filters_by_source(tmp_path):
    db = str(tmp_path / "d.db")
    _seed(db)
    log_trade_open(
        {"signal_id": None, "ticker": "CCC", "direction": "LONG", "entry": 10, "stop": 9,
         "target": 12, "shares": 5, "entry_bar": 1},
        db_path=db, source="backtest",
    )
    close_trade(
        # the trade above is the 3rd row inserted into a fresh db (id=3)
        3, {"exit_price": 12, "outcome": "WIN", "pnl": 500.0, "exit_bar": 5, "bars_held": 4},
        db_path=db,
    )
    c = create_app(db_path=db).test_client()

    live = c.get("/api/metrics?source=live").get_json()
    backtest = c.get("/api/metrics?source=backtest").get_json()
    unfiltered = c.get("/api/metrics").get_json()

    assert live["n_closed"] == 1
    assert live["total_pnl"] == 40.0
    assert backtest["n_closed"] == 1
    assert backtest["total_pnl"] == 500.0
    # no source filter still blends live + backtest, same as before this endpoint had one
    assert unfiltered["n_closed"] == 2
    assert unfiltered["total_pnl"] == 540.0


def test_open_trades_endpoint(tmp_path):
    data = _client(tmp_path).get("/api/open").get_json()
    assert len(data) == 1 and data[0]["ticker"] == "BBB"


def test_trades_and_signals_endpoints(tmp_path):
    c = _client(tmp_path)
    assert len(c.get("/api/trades").get_json()) == 2   # one closed + one open
    assert len(c.get("/api/signals").get_json()) == 1


def test_empty_db_does_not_error(tmp_path):
    db = str(tmp_path / "empty.db")
    init_db(db)
    c = create_app(db_path=db).test_client()
    assert c.get("/").status_code == 200
    m = c.get("/api/metrics").get_json()
    assert m["n_closed"] == 0
    assert c.get("/api/trades").get_json() == []


def test_signals_endpoint_respects_limit(tmp_path):
    db = str(tmp_path / "d.db")
    _seed(db)
    for _ in range(5):
        log_signal({"ticker": "CCC", "direction": "WAIT", "confidence": 0.5,
                    "entry": 10, "indicators_json": "{}"}, db_path=db)
    c = create_app(db_path=db).test_client()
    assert len(c.get("/api/signals?limit=3").get_json()) == 3
    assert len(c.get("/api/signals").get_json()) == 6


def test_signals_endpoint_filters_by_source(tmp_path):
    db = str(tmp_path / "d.db")
    _seed(db)
    log_signal({"ticker": "OLD", "direction": "LONG", "confidence": 0.7,
                "entry": 10, "indicators_json": "{}"}, db_path=db, source="backtest")
    c = create_app(db_path=db).test_client()
    live = c.get("/api/signals?source=live").get_json()
    backtest = c.get("/api/signals?source=backtest").get_json()
    assert len(live) == 1 and live[0]["ticker"] == "AAA"
    assert len(backtest) == 1 and backtest[0]["ticker"] == "OLD"


def test_signals_endpoint_rejects_bad_limit(tmp_path):
    db = str(tmp_path / "d.db")
    _seed(db)
    c = create_app(db_path=db).test_client()
    assert c.get("/api/signals?limit=notanumber").status_code == 400


def _one_signal_db(tmp_path, **overrides):
    db = str(tmp_path / "e.db")
    init_db(db)
    signal = {"ticker": "NVDA", "direction": "LONG", "confidence": 0.83, "entry": 100,
              "stop": 98, "target": 104, "rr": 2.0,
              "indicators_json": json.dumps({"votes": {"rsi": "bull", "macd": "bull"},
                                             "tally": {"bull": 5, "bear": 1, "neutral": 0}}),
              "reasoning": "template text", "synthesis_source": "template"}
    signal.update(overrides)
    sid = log_signal(signal, bar_timestamp="2026-06-10T14:30:00", db_path=db)
    return create_app(db_path=db).test_client(), db, sid


def _stored(db, sid):
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT reasoning, synthesis_source FROM signals WHERE id = ?", (sid,)
    ).fetchone()
    conn.close()
    return row


def test_explain_synthesizes_and_persists(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(llm_synthesis, "_anthropic_reasoning",
                        lambda s: ("five of six lean bullish", "anthropic:test-model"))
    client, db, sid = _one_signal_db(tmp_path)

    body = client.post("/api/signals/%d/explain" % sid).get_json()

    assert body["reasoning"] == "five of six lean bullish"
    assert body["synthesis_source"] == "anthropic:test-model"
    assert body["cached"] is False
    assert _stored(db, sid) == ("five of six lean bullish", "anthropic:test-model")


def test_explain_second_call_is_cached_and_costs_nothing(tmp_path, monkeypatch):
    calls = []

    def counted(signal):
        calls.append(signal)
        return "generated once", "anthropic:test-model"

    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(llm_synthesis, "_anthropic_reasoning", counted)
    client, _, sid = _one_signal_db(tmp_path)

    client.post("/api/signals/%d/explain" % sid)
    body = client.post("/api/signals/%d/explain" % sid).get_json()

    assert len(calls) == 1, "a cached row must not hit the provider again"
    assert body["cached"] is True
    assert body["reasoning"] == "generated once"


def test_explain_does_not_persist_a_provider_failure(tmp_path, monkeypatch):
    def boom(signal):
        raise RuntimeError("api down")

    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(llm_synthesis, "_anthropic_reasoning", boom)
    client, db, sid = _one_signal_db(tmp_path)

    body = client.post("/api/signals/%d/explain" % sid).get_json()

    assert body["synthesis_source"].startswith("template (fell back from anthropic")
    # Row is untouched, so the next request retries rather than caching the failure.
    assert _stored(db, sid) == ("template text", "template")


def test_explain_unknown_signal_is_404(tmp_path):
    client, _, _ = _one_signal_db(tmp_path)
    assert client.post("/api/signals/9999/explain").status_code == 404

import json
import sqlite3
import sys

import pandas as pd
import pytest

import config
from data.sessions import calendar, session_bounds
from research.shadow import ShadowRunner, replay_shadow
from trades.executor import PaperBroker


REGISTRATION = {"operator": "fixture-operator", "prospective_start": "2026-06-10T13:30Z",
                "review_after_completed_sessions": 60}


def signal(symbol, _window):
    return {"ticker": symbol, "direction": "LONG", "entry": 100, "stop": 99, "target": 102}


def bar(timestamp, volume=100, close=100):
    return {"timestamp": timestamp, "open": close, "high": close, "low": close, "close": close, "volume": volume}


def prior_history(day):
    days = [str(value.date()) for value in calendar(int(day[:4])).sessions if str(value.date()) < day][-20:]
    rows = []
    for value in days:
        opening, closing = session_bounds(value + "T17:00Z")
        rows.extend(bar(timestamp, 100) for timestamp in pd.date_range(opening, closing - pd.Timedelta(minutes=5), freq="5min"))
    return days, {"AAA": rows}


def session_bars(day, volume=100):
    opening, closing = session_bounds(day + "T17:00Z")
    return [bar(timestamp, volume) for timestamp in pd.date_range(opening, closing - pd.Timedelta(minutes=5), freq="5min")]


def test_rvol_history_is_explicit_and_restart_duplicate_is_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WARMUP_BARS", 1)
    days, history = prior_history("2026-06-10")
    db = str(tmp_path / "shadow.db")
    runner = ShadowRunner(["AAA"], db_path=db, feed_identity="fixture:IEX", registration=REGISTRATION,
                          candidate_factory=signal, candidate_factory_identity="fixture-v1")
    runner.initialize_history(history, completed_sessions=days, feed_identity="fixture:IEX")
    assert runner.artifact()["completed_sessions"] == 0
    assert runner.artifact()["seeded_history_sessions"] == 20
    with pytest.raises(ValueError, match="one-time"):
        runner.initialize_history(history, completed_sessions=days, feed_identity="fixture:IEX")
    event = {"AAA": bar("2026-06-10T13:30Z", 150)}
    assert runner.process_completed_batch(event)["processed"]
    with sqlite3.connect(db) as conn:
        baseline, rvol = [json.loads(row[0]) for row in conn.execute(
            "SELECT gate_json FROM shadow_candidates WHERE variant IN ('baseline','rvol') ORDER BY variant")]
    assert baseline["accepted"] and rvol["checks"]["rvol"]["observations"] == 20
    assert rvol["checks"]["rvol"]["value"] == 1.5
    restarted = ShadowRunner(["AAA"], db_path=db, feed_identity="fixture:IEX", registration=REGISTRATION,
                             run_id=runner.run_id, candidate_factory=signal, candidate_factory_identity="fixture-v1")
    assert restarted.process_completed_batch(event)["duplicate"]
    assert restarted.artifact()["variants"]["baseline"]["account"] != restarted.artifact()["variants"]["rvol"]["account"]


def test_shadow_is_offline_stale_and_replay_parity(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WARMUP_BARS", 1)
    monkeypatch.setattr(config, "BROKER", "alpaca")
    class NoBrokerClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("shadow must never instantiate a broker client")
    monkeypatch.setitem(sys.modules, "trades.alpaca_broker", type("SpyModule", (), {"AlpacaBroker": NoBrokerClient}))
    def order_submission_spy(*_args, **_kwargs):
        raise AssertionError("shadow must never submit an order")
    monkeypatch.setattr(PaperBroker, "submit_order", order_submission_spy, raising=False)
    event = {"AAA": bar("2026-06-10T13:30Z", 150)}
    result = replay_shadow([event], symbols=["AAA"], db_path=str(tmp_path / "replay.db"),
                           feed_identity="fixture:IEX", registration=REGISTRATION, candidate_factory=signal,
                           candidate_factory_identity="fixture-v1")
    live = ShadowRunner(["AAA"], db_path=str(tmp_path / "live.db"), feed_identity="fixture:IEX",
                        registration=REGISTRATION, candidate_factory=signal, candidate_factory_identity="fixture-v1")
    assert live.process_completed_batch(event)["event_sha256"]
    assert live.process_completed_batch({"AAA": bar("2026-06-10T13:35Z")})["processed"]
    assert result["variants"].keys() == live.artifact()["variants"].keys()
    stale = live.process_completed_batch({"AAA": bar("2026-06-10T13:40Z")}, received_at="2026-06-10T14:00Z")
    assert stale["stale"]
    with sqlite3.connect(str(tmp_path / "live.db")) as conn:
        assert conn.execute("SELECT count(*) FROM shadow_candidates WHERE status='rejected'").fetchone()[0] >= 2


def test_replay_preserves_original_receipt_time_and_stale_decision(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WARMUP_BARS", 1)
    event = {"AAA": bar("2026-06-10T13:30Z")}
    received = "2026-06-10T14:00Z"
    live = ShadowRunner(["AAA"], db_path=str(tmp_path / "live-stale.db"), feed_identity="fixture:IEX",
                        registration=REGISTRATION, candidate_factory=signal, candidate_factory_identity="fixture-v1")
    live.process_completed_batch(event, received_at=received)
    replay_shadow([{"bars": event, "received_at": received}], symbols=["AAA"], db_path=str(tmp_path / "replay-stale.db"),
                  feed_identity="fixture:IEX", registration=REGISTRATION, candidate_factory=signal,
                  candidate_factory_identity="fixture-v1")
    with sqlite3.connect(str(tmp_path / "live-stale.db")) as live_db, sqlite3.connect(str(tmp_path / "replay-stale.db")) as replay_db:
        live_rows = live_db.execute("SELECT eligibility_json,gate_json,status FROM shadow_candidates ORDER BY variant").fetchall()
        replay_rows = replay_db.execute("SELECT eligibility_json,gate_json,status FROM shadow_candidates ORDER BY variant").fetchall()
    assert [(json.loads(row[0])["reason"], row[1], row[2]) for row in live_rows] == [
        (json.loads(row[0])["reason"], row[1], row[2]) for row in replay_rows]


def test_entry_does_not_trigger_exit_until_next_observation_and_cash_is_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WARMUP_BARS", 1)
    runner = ShadowRunner(["AAA"], db_path=str(tmp_path / "cash.db"), feed_identity="fixture:IEX",
                          registration=REGISTRATION, candidate_factory=signal, candidate_factory_identity="fixture-v1")
    runner.process_completed_batch({"AAA": bar("2026-06-10T13:30Z")})  # baseline queues; RVOL lacks history
    runner.process_completed_batch({"AAA": {**bar("2026-06-10T13:35Z"), "high": 103}})  # baseline opens after exit scan
    baseline = runner.variants["baseline"]["broker"]
    assert baseline.has_open("AAA") and "pending_exit" not in baseline.open_positions["AAA"]
    runner.process_completed_batch({"AAA": {**bar("2026-06-10T13:40Z"), "high": 103}})
    assert baseline.open_positions["AAA"]["pending_exit"]["reason"] == "target"
    runner.process_completed_batch({"AAA": bar("2026-06-10T13:45Z", close=102)})
    assert baseline.capital > runner.variants["rvol"]["broker"].capital


def test_history_and_events_reject_future_incomplete_duplicate_and_rollback(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WARMUP_BARS", 1)
    runner = ShadowRunner(["AAA"], db_path=str(tmp_path / "validity.db"), feed_identity="fixture:IEX",
                          registration=REGISTRATION, candidate_factory=signal, candidate_factory_identity="fixture-v1")
    days, history = prior_history("2026-06-10")
    with pytest.raises(ValueError, match="incomplete"):
        runner.initialize_history({"AAA": history["AAA"][:-1]}, completed_sessions=days, feed_identity="fixture:IEX")
    with pytest.raises(ValueError, match="completed"):
        runner.process_completed_batch({"AAA": bar("2026-06-10T13:30Z")}, received_at="2026-06-10T13:34Z")
    with pytest.raises(ValueError, match="aligned"):
        runner.process_completed_batch({"AAA": bar("2026-06-10T13:31Z")})
    def fail(*_args):
        raise RuntimeError("simulated crash")
    runner.candidate_factory = fail
    with pytest.raises(RuntimeError, match="simulated crash"):
        runner.process_completed_batch({"AAA": bar("2026-06-10T13:30Z")})
    assert runner.watermark is None
    with sqlite3.connect(str(tmp_path / "validity.db")) as conn:
        assert conn.execute("SELECT count(*) FROM shadow_events").fetchone()[0] == 0
    runner.candidate_factory = signal
    assert runner.process_completed_batch({"AAA": bar("2026-06-10T13:30Z")})["processed"]


def test_capture_cannot_consume_pre_registration_bars_or_late_history(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WARMUP_BARS", 1)
    runner = ShadowRunner(["AAA"], db_path=str(tmp_path / "causal.db"), feed_identity="fixture:IEX",
                          registration=REGISTRATION, candidate_factory=signal, candidate_factory_identity="fixture-v1")
    days, history = prior_history("2026-06-10")
    runner.initialize_history(history, completed_sessions=days, feed_identity="fixture:IEX")
    with pytest.raises(ValueError, match="precedes"):
        runner.process_completed_batch({"AAA": bar("2026-06-08T13:30Z")})
    runner.process_completed_batch({"AAA": bar("2026-06-10T13:30Z")})
    with pytest.raises(ValueError, match="locked"):
        runner.initialize_history(history, completed_sessions=days, feed_identity="fixture:IEX")


def test_restart_rejects_config_change_and_future_events_do_not_change_prior_candidates(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WARMUP_BARS", 1)
    db = str(tmp_path / "frozen.db")
    runner = ShadowRunner(["AAA"], db_path=db, feed_identity="fixture:IEX", registration=REGISTRATION,
                          candidate_factory=signal, candidate_factory_identity="fixture-v1")
    runner.process_completed_batch({"AAA": bar("2026-06-10T13:30Z")})
    with sqlite3.connect(db) as conn:
        before = conn.execute("SELECT raw_json,gate_json FROM shadow_candidates ORDER BY variant").fetchall()
    runner.process_completed_batch({"AAA": bar("2026-06-10T13:35Z", volume=999999)})
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT raw_json,gate_json FROM shadow_candidates WHERE timestamp=? ORDER BY variant", ("2026-06-10T13:30:00+00:00",)).fetchall() == before
    monkeypatch.setattr(config, "POSITION_PCT", config.POSITION_PCT / 2)
    with pytest.raises(ValueError, match="frozen shadow"):
        ShadowRunner(["AAA"], db_path=db, feed_identity="fixture:IEX", registration=REGISTRATION,
                     run_id=runner.run_id, candidate_factory=signal, candidate_factory_identity="fixture-v1")


def test_expired_candidates_do_not_cross_sessions_and_rvol_handles_early_close_and_dst(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WARMUP_BARS", 1)
    runner = ShadowRunner(["AAA"], db_path=str(tmp_path / "expiry.db"), feed_identity="fixture:IEX",
                          registration=REGISTRATION, candidate_factory=signal, candidate_factory_identity="fixture-v1")
    runner.process_completed_batch({"AAA": bar("2026-06-10T13:30Z")})
    runner.process_completed_batch({"AAA": bar("2026-06-11T13:30Z")})
    assert not runner.variants["baseline"]["broker"].has_open("AAA")
    assert runner.artifact()["completed_sessions"] == 0
    with sqlite3.connect(str(tmp_path / "expiry.db")) as conn:
        assert conn.execute("SELECT count(*) FROM shadow_issues WHERE reason='incomplete_session'").fetchone()[0] == 1
    registration = {**REGISTRATION, "prospective_start": "2026-11-30T19:30Z"}
    days, history = prior_history("2026-11-30")
    early = ShadowRunner(["AAA"], db_path=str(tmp_path / "early.db"), feed_identity="fixture:IEX",
                         registration=registration, candidate_factory=signal, candidate_factory_identity="fixture-v1")
    early.initialize_history(history, completed_sessions=days, feed_identity="fixture:IEX")
    early.process_completed_batch({"AAA": bar("2026-11-30T19:30Z", 150)})
    with sqlite3.connect(str(tmp_path / "early.db")) as conn:
        detail = json.loads(conn.execute("SELECT gate_json FROM shadow_candidates WHERE variant='rvol'").fetchone()[0])
    assert detail["checks"]["rvol"]["observations"] == 19  # Black Friday lacks this late bucket.
    march_registration = {**REGISTRATION, "prospective_start": "2026-03-10T14:00Z"}
    days, history = prior_history("2026-03-10")
    dst = ShadowRunner(["AAA"], db_path=str(tmp_path / "dst.db"), feed_identity="fixture:IEX",
                       registration=march_registration, candidate_factory=signal, candidate_factory_identity="fixture-v1")
    dst.initialize_history(history, completed_sessions=days, feed_identity="fixture:IEX")
    dst.process_completed_batch({"AAA": bar("2026-03-10T14:00Z", 150)})
    with sqlite3.connect(str(tmp_path / "dst.db")) as conn:
        detail = json.loads(conn.execute("SELECT gate_json FROM shadow_candidates WHERE variant='rvol'").fetchone()[0])
    assert detail["checks"]["rvol"]["value"] == 1.5


def test_full_prospective_session_is_counted_without_next_day(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WARMUP_BARS", 1)
    runner = ShadowRunner(["AAA"], db_path=str(tmp_path / "complete.db"), feed_identity="fixture:IEX",
                          registration=REGISTRATION, candidate_factory=signal, candidate_factory_identity="fixture-v1")
    for current in session_bars("2026-06-10"):
        assert runner.process_completed_batch({"AAA": current})["processed"]
    artifact = runner.artifact()
    assert artifact["completed_sessions"] == 1
    assert artifact["seeded_history_sessions"] == 0

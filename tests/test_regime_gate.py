"""T07 regime eligibility fixtures; all data is synthetic and offline."""

import json

import pandas as pd
import pytest

from data.sessions import utc
from research import REGIME_VARIANTS, run_comparison
from signals.indicators import compute_indicators
from signals.quality import ResearchGate
from signals.regime import (BEAR, BULL, CHOPPY, UNKNOWN, classify_context,
                            regime_eligibility)


def _ind(close, sma20, sma50):
    return {"close": close, "sma20": sma20, "sma50": sma50}


@pytest.mark.parametrize(
    "regime,direction,accepted",
    [(BULL, "LONG", True), (BULL, "SHORT", False),
     (BEAR, "LONG", False), (BEAR, "SHORT", True),
     (CHOPPY, "LONG", False), (CHOPPY, "SHORT", False),
     (UNKNOWN, "LONG", False), (UNKNOWN, "SHORT", False)],
)
def test_regime_gate_truth_table(regime, direction, accepted):
    context = {"regime": regime, "known": regime != UNKNOWN, "reason": "fixture"}
    result = regime_eligibility(direction, context)
    assert result["accepted"] is accepted
    assert result["reason"]


def test_missing_and_stale_spy_are_unknown_and_rejected():
    missing = classify_context(None)
    stale = classify_context(_ind(110, 105, 100), stale=True)
    for context, reason in ((missing, "missing_spy"), (stale, "stale_spy")):
        assert context["regime"] == UNKNOWN
        assert context["known"] is False
        assert context["reason"] == reason
        result = regime_eligibility("LONG", context)
        assert result["accepted"] is False
        assert result["reason"] == "unknown_context"


def _bar(ts, close, volume=1000):
    return {"timestamp": ts, "open": close, "high": close + 1,
            "low": close - 1, "close": close, "volume": volume}


def _causal_fixture():
    timestamps = pd.date_range("2026-06-10T13:30Z", periods=65, freq="5min")
    # All context bars trend upward; 50 bars make SMA50 decision-available.
    return {
        symbol: pd.DataFrame([_bar(ts, 100 + i + offset) for i, ts in enumerate(timestamps)])
        for symbol, offset in (("AAA", 10), ("SPY", 0), ("QQQ", 1))
    }, timestamps


def test_regime_gate_replay_is_causal_and_replay_live_parity():
    bars, timestamps = _causal_fixture()
    decision_at = timestamps[54] + pd.Timedelta(minutes=5)
    gate = ResearchGate(bars, "regime")
    replay = gate("AAA", {}, decision_at, "LONG")
    available = {symbol: frame[frame.timestamp <= timestamps[54]]
                 for symbol, frame in bars.items()}
    live_context = classify_context(
        compute_indicators(available["SPY"]),
        compute_indicators(available["QQQ"]),
    )
    live = regime_eligibility("LONG", live_context)
    replay_check = replay[1]["checks"]["regime"]
    assert replay_check["accepted"] == live["accepted"]
    assert replay_check["regime"] == live["regime"]
    assert replay_check["reason"] == live["reason"]
    assert replay[0] is True

    future = {symbol: frame.copy() for symbol, frame in bars.items()}
    for frame in future.values():
        frame.loc[frame.timestamp > timestamps[54], "close"] = 1.0
    assert ResearchGate(future, "regime")("AAA", {}, decision_at, "LONG") == replay


def test_regime_freshness_uses_decision_timestamp_at_boundary():
    bars, timestamps = _causal_fixture()
    bars = {symbol: frame[frame.timestamp <= timestamps[54]].copy()
            for symbol, frame in bars.items()}
    # At 15 minutes after the last context bar, both replay and live must reject.
    decision_at = timestamps[54] + pd.Timedelta(minutes=15)
    accepted, detail = ResearchGate(bars, "regime")("AAA", {}, decision_at, "LONG")
    assert accepted is False
    assert detail["checks"]["regime"]["context"]["reason"] == "stale_spy"


def test_regime_gate_missing_context_detail_is_persistable():
    timestamps = pd.date_range("2026-06-10T13:30Z", periods=3, freq="5min")
    bars = {"AAA": pd.DataFrame([_bar(ts, 100) for ts in timestamps])}
    accepted, detail = ResearchGate(bars, "regime")(
        "AAA", {}, timestamps[-1] + pd.Timedelta(minutes=5), "LONG")
    assert accepted is False
    assert detail["reason"] == "regime_gate:unknown_context"
    assert detail["checks"]["regime"]["context"]["reason"] == "missing_spy"
    assert json.dumps(detail, allow_nan=False)


def test_regime_runner_declares_separate_variants(tmp_path, monkeypatch):
    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures"
    monkeypatch.setattr("config.SPREAD_BPS", 2)
    monkeypatch.setattr("config.SLIPPAGE_BPS", 1)
    output = tmp_path / "regime"
    summary = run_comparison(fixture / "bars.json", fixture / "windows.json", output,
                             allow_synthetic=True, experiment="regime",
                             registration_path=fixture / "regime_registration.json")
    assert REGIME_VARIANTS == ("baseline", "regime")
    assert {row["variant"] for row in summary} == set(REGIME_VARIANTS)
    assert all("opportunity_loss" in row["diagnostics"] for row in summary)
    protocol = json.loads((output / "protocol.json").read_text())
    assert protocol["experiment"] == "regime"
    assert protocol["regime_registration"]["status"] == "registered"
    assert {row["variant"] for row in protocol["registered_trials"]} == set(REGIME_VARIANTS)
    assert all("rvol" not in row["variant"] for row in protocol["registered_trials"])
    assert "Opportunity loss" in (output / "comparison.md").read_text()


def test_regime_runner_blocks_without_registration(tmp_path):
    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures"
    with pytest.raises(ValueError, match="requires --registration"):
        run_comparison(fixture / "bars.json", fixture / "windows.json", tmp_path / "blocked",
                       allow_synthetic=True, experiment="regime")


def test_regime_registration_rejects_extra_holdout_window(tmp_path):
    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures"
    windows = json.loads((fixture / "windows.json").read_text())
    windows.append({
        "name": "unregistered_holdout",
        "start": "2026-06-11T13:30Z",
        "end": "2026-06-11T20:00Z",
        "role": "holdout",
    })
    windows_path = tmp_path / "windows.json"
    windows_path.write_text(json.dumps(windows))
    with pytest.raises(ValueError, match="exactly one holdout"):
        run_comparison(fixture / "bars.json", windows_path, tmp_path / "blocked-extra",
                       allow_synthetic=True, experiment="regime",
                       registration_path=fixture / "regime_registration.json")

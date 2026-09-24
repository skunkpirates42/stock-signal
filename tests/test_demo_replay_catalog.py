import importlib.util
import shutil
from pathlib import Path

import pandas as pd
import pytest

import config
from backtest import run_portfolio
from dashboard.app import create_app
from demo.replay_catalog import (COST_PROFILES, DATASETS, TRADER_WINDOW_BARS, ReplayRequestRejected,
                                 TEMPLATE_VERSION, build_replay_request, dataset_is_available,
                                 request_fingerprint, strategy_version_for)

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("engine_demo_contract", ROOT / "docs/engine-demo/validate.py")
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)

FIXTURE_ID = "6f1d0a52-3c1b-4f7e-9a51-0c6a1f4e2b10"
MARKET_ID = "b8e4c7d2-51a9-4c36-8f0e-2d7a9e3c4b61"


def fixture_request(**overrides):
    return {"strategy_id": "stock-signal", "dataset_id": FIXTURE_ID, "window_id": "fixture-day-2",
            "cost_profile_id": "base-v2", "idempotency_key": "click-0001", **overrides}


def test_replay_catalog_exposes_only_approved_choices(tmp_path):
    response = create_app(db_path=str(tmp_path / "journal.db"), demo_db_path=str(tmp_path / "index.db"),
                          demo_job_db_path=str(tmp_path / "jobs.db")).test_client().get("/api/demo/v1/replay-catalog")
    assert response.status_code == 200
    catalog = response.get_json()["data"]
    assert catalog["strategy"] == {"id": "stock-signal", "label": "Stock Signal baseline", "editable_fields": []}
    assert {item["id"] for item in catalog["datasets"]} == set(DATASETS)
    assert {item["id"] for item in catalog["cost_profiles"]} == set(COST_PROFILES)
    assert catalog["datasets"][0]["windows"][0]["id"] == "fixture-day-2"
    assert "relative_path" not in str(catalog)


def test_fixture_request_selects_warmup_and_window_and_validates_against_a1():
    built = build_replay_request(fixture_request())
    run = built.normalized_run
    contract.validate(contract.envelope(run))
    start = pd.Timestamp("2026-06-10T13:30:00Z")
    assert built.evaluation_start == start
    for frame in built.bars.values():
        warmup = frame[frame.timestamp < start]
        evaluation = frame[frame.timestamp >= start]
        assert config.WARMUP_BARS <= len(warmup) <= TRADER_WINDOW_BARS
        assert evaluation.timestamp.max() < pd.Timestamp("2026-06-10T20:00:00Z")
        assert len(evaluation) == 78
    assert run["window"] == {"name": "fixture-day-2", "role": "evaluation",
                             "start": "2026-06-10T13:30:00+00:00", "end_exclusive": "2026-06-10T20:00:00+00:00"}
    assert run["observed_bounds"]["first_bar"]["value"] == "2026-06-09T13:30:00+00:00"
    assert run["dataset_sha256"]["value"] == DATASETS[FIXTURE_ID].sha256
    assert run["cost_policy"] == COST_PROFILES["base-v2"].policy_record()
    assert run["feed"]["value"] == "synthetic:seeded-fixture"
    provenance = run["provenance"]
    assert (provenance["synthetic"], provenance["retrospective"], provenance["evaluation"]) == (
        True, False, "synthetic_correctness")
    assert run["strategy_version"]["availability"] == "available"


def test_selected_data_digest_matches_the_replay_manifest(tmp_path):
    built = build_replay_request(fixture_request())
    result = run_portfolio(built.bars, str(tmp_path / "run.db"), feed=built.normalized_run["feed"]["value"],
                           evaluation_start=built.evaluation_start)
    assert result["manifest"]["dataset_sha256"] == built.normalized_run["selected_data_sha256"]["value"]


def test_market_windows_are_labelled_retrospective_when_dataset_present():
    if not dataset_is_available(DATASETS[MARKET_ID]):
        pytest.skip("ignored local Alpaca dataset is not present")
    built = build_replay_request(fixture_request(dataset_id=MARKET_ID, window_id="holdout", cost_profile_id="adverse-v2"))
    contract.validate(contract.envelope(built.normalized_run))
    provenance = built.normalized_run["provenance"]
    assert (provenance["retrospective"], provenance["synthetic"], provenance["evaluation"]) == (
        True, False, "retrospective")
    assert built.normalized_run["cost_policy"]["spread_bps"] == 5.0


@pytest.mark.parametrize("overrides, code", [
    ({"dataset_path": "/etc/passwd"}, "unexpected_field"),
    ({"spread_bps": 0}, "unexpected_field"),
    ({"strategy_id": "custom"}, "unknown_strategy"),
    ({"dataset_id": "../tests/fixtures/bars.json"}, "unknown_dataset"),
    ({"window_id": "development"}, "unknown_window"),
    ({"cost_profile_id": "zero"}, "unknown_cost_profile"),
    ({"idempotency_key": "short"}, "invalid_idempotency_key"),
    ({"idempotency_key": "has space in it"}, "invalid_idempotency_key"),
    ({"window_id": 1}, "invalid_request"),
])
def test_forbidden_or_unapproved_inputs_are_rejected(overrides, code):
    with pytest.raises(ReplayRequestRejected) as rejected:
        build_replay_request(fixture_request(**overrides))
    assert rejected.value.code == code


def test_missing_field_and_non_object_are_rejected():
    request = fixture_request()
    del request["cost_profile_id"]
    with pytest.raises(ReplayRequestRejected, match="missing"):
        build_replay_request(request)
    with pytest.raises(ReplayRequestRejected):
        build_replay_request(["stock-signal"])


def test_changed_or_missing_dataset_bytes_are_rejected(tmp_path):
    fixture_dir = tmp_path / "tests" / "fixtures"
    fixture_dir.mkdir(parents=True)
    with pytest.raises(ReplayRequestRejected) as missing:
        build_replay_request(fixture_request(), root=tmp_path)
    assert missing.value.code == "dataset_unavailable"
    shutil.copy(ROOT / "tests/fixtures/bars.meta.json", fixture_dir / "bars.meta.json")
    (fixture_dir / "bars.json").write_bytes((ROOT / "tests/fixtures/bars.json").read_bytes() + b" ")
    with pytest.raises(ReplayRequestRejected) as changed:
        build_replay_request(fixture_request(), root=tmp_path)
    assert changed.value.code == "dataset_changed"


def test_changed_feed_metadata_is_rejected_although_bars_match(tmp_path):
    fixture_dir = tmp_path / "tests" / "fixtures"
    fixture_dir.mkdir(parents=True)
    shutil.copy(ROOT / "tests/fixtures/bars.json", fixture_dir / "bars.json")
    (fixture_dir / "bars.meta.json").write_text('{"feed":"alpaca:sip"}')
    with pytest.raises(ReplayRequestRejected) as changed:
        build_replay_request(fixture_request(), root=tmp_path)
    assert changed.value.code == "dataset_changed"


@pytest.mark.parametrize("meta", ["{not json", "[]"])
def test_unreadable_feed_metadata_is_rejected_as_changed(tmp_path, meta):
    fixture_dir = tmp_path / "tests" / "fixtures"
    fixture_dir.mkdir(parents=True)
    shutil.copy(ROOT / "tests/fixtures/bars.json", fixture_dir / "bars.json")
    (fixture_dir / "bars.meta.json").write_text(meta)
    with pytest.raises(ReplayRequestRejected) as changed:
        build_replay_request(fixture_request(), root=tmp_path)
    assert changed.value.code == "dataset_changed"


def test_retained_strategy_configuration_reproduces_strategy_version():
    built = build_replay_request(fixture_request())
    retained = built.strategy_configuration
    assert retained["template_version"] == TEMPLATE_VERSION
    assert retained["source_sha256"] == built.normalized_run["code"]["source_sha256"]["value"]
    assert retained["configuration"]["WARMUP_BARS"] == config.WARMUP_BARS
    assert not {"SPREAD_BPS", "SLIPPAGE_BPS", "FEE_PER_SHARE", "BROKER"} & set(retained["configuration"])
    assert strategy_version_for(retained) == built.normalized_run["strategy_version"]["value"]
    changed = {**retained, "configuration": {**retained["configuration"], "WARMUP_BARS": 1}}
    assert strategy_version_for(changed) != built.normalized_run["strategy_version"]["value"]


def test_window_without_enough_warmup_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "WARMUP_BARS", TRADER_WINDOW_BARS)
    with pytest.raises(ReplayRequestRejected) as rejected:
        build_replay_request(fixture_request())
    assert rejected.value.code == "insufficient_warmup"


def test_fingerprint_ignores_idempotency_key_but_not_inputs():
    assert request_fingerprint(fixture_request()) == request_fingerprint(fixture_request(idempotency_key="click-0002"))
    assert request_fingerprint(fixture_request()) != request_fingerprint(fixture_request(cost_profile_id="adverse-v2"))


def test_cost_profiles_inject_catalog_values_only():
    assert COST_PROFILES["adverse-v2"].child_environment() == {
        "SPREAD_BPS": "5.0", "SLIPPAGE_BPS": "2.0", "FEE_PER_SHARE": "0.0"}
    assert all(any((p.spread_bps, p.slippage_bps_per_fill, p.fee_per_share_per_fill)) for p in COST_PROFILES.values())

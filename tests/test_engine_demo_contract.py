"""Portable offline A1 contracts; saved ignored research directories are optional."""
import copy
import importlib.util
from pathlib import Path

import pytest
from jsonschema import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("engine_demo_contract", ROOT / "docs/engine-demo/validate.py")
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)


def test_synthetic_omissions_preserve_zero_and_unavailable():
    records = contract.synthetic_records()
    contract.validate(records)
    result = records[3]["data"]
    assert result["provenance"]["synthetic"] is True
    assert result["metrics"]["realized_net_pnl"]["observation"] == contract.available(0)
    assert result["metrics"]["marked_net_pnl"]["observation"]["value"] is None
    assert result["metrics"]["borrow_cost"]["observation"]["reason"] == "not_modeled"
    assert result["metrics"]["fees"]["observation"]["value"] is None
    assert records[2]["data"]["code"]["revision"]["value"] is None
    assert records[4]["data"]["created_at"]["value"] is None


@pytest.mark.parametrize("mutation", [
    lambda result: result["metrics"]["realized_net_pnl"].pop("basis"),
    lambda result: result["metrics"]["borrow_cost"]["observation"].update(value=0),
    lambda result: result["provenance"].update(synthetic=False),
    lambda result: result["window"].update(start="2026-01-05T00:00:00-05:00"),
    lambda result: result.update(id="/private/saved/result.json"),
    lambda result: result.update(absolute_path="/private/saved/result.json"),
    lambda result: result["metrics"]["realized_net_pnl"]["observation"].update(value="0"),
    lambda result: result["metrics"]["realized_net_pnl"].update(source_pointer=None),
])
def test_schema_rejects_unsafe_or_ambiguous_records(mutation):
    records = contract.synthetic_records()
    mutation(records[3]["data"])
    with pytest.raises(ValidationError):
        contract.validate(records)


def test_retrospective_flag_cannot_be_removed_from_examined_evaluation():
    records = contract.synthetic_records()
    for record in records:
        provenance = record["data"].get("provenance")
        if provenance:
            provenance.update(synthetic=False, retrospective=True, evaluation="retrospective")
    contract.validate(records)
    records[3]["data"]["provenance"]["retrospective"] = False
    with pytest.raises(ValidationError):
        contract.validate(records)


def test_accounting_gap_cannot_be_changed_to_available_zero():
    records = contract.synthetic_records()
    metric = records[3]["data"]["metrics"]["borrow_cost"]
    metric.update(observation=contract.available(0), source_pointer="/invented/borrow_cost")
    with pytest.raises(ValueError, match="Unresolved accounting"):
        contract.validate(records)


def test_window_is_nonempty():
    records = contract.synthetic_records()
    window = records[3]["data"]["window"]
    window["end_exclusive"] = window["start"]
    with pytest.raises(ValueError, match="Window start"):
        contract.validate(records)


def test_single_envelope_uses_schema_and_semantic_validation():
    result = contract.synthetic_records()[3]
    contract.validate(result)
    window = result["data"]["window"]
    window["end_exclusive"] = window["start"]
    with pytest.raises(ValueError, match="Window start"):
        contract.validate(result)


def test_schema_complete_accounting_requires_no_unresolved_fields():
    result = contract.synthetic_records()[3]
    result["data"]["accounting"]["coverage"] = "complete"
    with pytest.raises(ValidationError):
        contract.VALIDATOR.validate(result)
    result["data"]["accounting"]["unresolved"] = []
    contract.VALIDATOR.validate(result)


@pytest.mark.parametrize("metric_name", contract.SCHEMA["$defs"]["result"]["properties"]["metrics"]["required"])
def test_schema_itself_rejects_wrong_named_metric_units(metric_name):
    result = contract.synthetic_records()[3]
    result["data"]["metrics"][metric_name]["unit"] = "multiple"
    with pytest.raises(ValidationError):
        contract.VALIDATOR.validate(result)


@pytest.mark.parametrize("mutation", [
    lambda wrapper: wrapper.pop("basis"),
    lambda wrapper: wrapper.pop("unit"),
    lambda wrapper: wrapper.pop("source_pointer"),
    lambda wrapper: wrapper.update(unit="fraction"),
    lambda wrapper: wrapper.update(values={"BULL": "profitable"}),
    lambda wrapper: wrapper["values"]["BULL"].pop("win_rate"),
    lambda wrapper: wrapper["values"]["BULL"].update(pnl="12.50"),
    lambda wrapper: wrapper["values"]["BULL"].update(n=1.5),
    lambda wrapper: wrapper["values"]["BULL"].update(wins=-1),
    lambda wrapper: wrapper["values"]["BULL"].update(win_rate=50),
    lambda wrapper: wrapper["values"]["BULL"].update(win_rate=-0.5),
])
def test_schema_rejects_malformed_available_regime_values(mutation):
    result = contract.synthetic_records()[3]
    wrapper = result["data"]["by_regime"]["value"]
    wrapper["values"] = {"BULL": {"n": 2, "wins": 1, "pnl": 12.5, "win_rate": 0.5}}
    contract.VALIDATOR.validate(result)
    mutation(wrapper)
    with pytest.raises(ValidationError):
        contract.VALIDATOR.validate(result)


def test_completed_status_requires_result_and_failed_status_requires_details():
    status = contract.synthetic_records()[-1]
    status["data"]["result_id"] = contract.unavailable()
    with pytest.raises(ValidationError):
        contract.validate([status])
    status["data"].update(origin="job", state="failed")
    with pytest.raises(ValidationError):
        contract.validate([status])
    status["data"]["failure"] = {"code": "worker_lost", "summary": "Worker lease expired.",
                                  "at": "2026-09-20T12:00:00Z", "retryable": False,
                                  "log_artifact_id": contract.unavailable()}
    contract.validate([status])


def test_artifact_references_do_not_accept_paths_or_database_downloads():
    artifact = contract.envelope({"record_type": "artifact", "id": contract.identifier("artifact"),
                                  "result_id": contract.identifier("result"), "kind": "comparison",
                                  "sha256": "a" * 64, "mime_type": "application/json", "byte_size": 20})
    contract.validate([artifact])
    changed = copy.deepcopy(artifact)
    changed["data"]["path"] = "../../.env"
    with pytest.raises(ValidationError):
        contract.validate([changed])
    artifact["data"].update(kind="database", mime_type="application/x-sqlite3")
    with pytest.raises(ValidationError):
        contract.validate([artifact])


@pytest.mark.parametrize("scenario", ["alpaca-iex-2026-base-v2", "alpaca-iex-2026-adverse-v2"])
def test_saved_v2_sources_validate_without_changes(scenario):
    directory = ROOT / "research-output" / scenario
    if not directory.is_dir():
        pytest.skip("Ignored local saved scenario is not bundled; portable fixture still runs")
    report = contract.check_saved(directory)
    assert report == {"scenario": scenario, "validated_rows": 8, "unchanged_files": 27,
                      "evaluation": "retrospective", "accounting": "incomplete"}

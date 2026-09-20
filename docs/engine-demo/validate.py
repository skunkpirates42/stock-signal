"""Offline A1 contract harness, not an importer, registry, API or replay runner.

Builds ephemeral read-model examples from explicitly selected legacy source files.
Never writes source artifacts or computes financial performance.
"""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from jsonschema import Draft202012Validator, FormatChecker

HERE = Path(__file__).resolve().parent
SCHEMA = json.loads((HERE / "v1.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
LEGACY_GAPS = ["dividend_cashflow", "borrow_cost", "taxes", "cost_decomposition"]


def available(value):
    return {"availability": "available", "value": value, "reason": None, "detail": None}


def unavailable(reason="not_recorded", detail="Not recorded in the selected source."):
    return {"availability": "unavailable", "value": None, "reason": reason, "detail": detail}


def recorded(source, key):
    return available(source[key]) if source.get(key) is not None else unavailable()


def identifier(value):
    # Deterministic UUIDs only for reproducible contract examples. A2 owns public IDs.
    return str(uuid5(NAMESPACE_URL, "urn:stock-signal:contract-example:" + value))


def envelope(data):
    return {"schema_version": 1, "data": data, "warnings": []}


def metric(value, unit, basis, pointer, missing=None):
    return {"observation": available(value) if value is not None else missing or unavailable(),
            "unit": unit, "basis": basis, "source_pointer": pointer if value is not None else None}


def normalize(protocol, row, manifest, marked, scenario, synthetic, row_index=0, marked_index=0):
    """Contract example projection; source omissions and saved numbers remain intact."""
    source_window = row["window"]
    window = {"name": source_window["name"], "role": source_window["role"],
              "start": source_window["start"], "end_exclusive": source_window["end"]}
    dataset_id = identifier(scenario + ":dataset")
    run_id = identifier(scenario + ":" + window["name"] + ":" + row["variant"])
    result_id = identifier(run_id + ":result")
    metadata = protocol.get("dataset_metadata", {})
    provenance = {
        "source": "backtest", "execution": "local_simulation", "historical": True,
        "retrospective": not synthetic, "synthetic": synthetic,
        "evaluation": "synthetic_correctness" if synthetic else "retrospective",
        "holdout_status": unavailable("not_registered", "No prospective registration and coverage record is provided."),
        "label_evidence": ["Hand-authored synthetic-source.json correctness fixture." if synthetic else
                           "docs/experiments/accounting-contract.md: January-August 2026 is examined research data."]}
    accounting = {"version": unavailable("unknown_legacy", "No accounting policy version in these saved sources."),
                  "mode": "recorded_costs_only", "coverage": "incomplete", "unresolved": LEGACY_GAPS.copy()}
    version = unavailable("unknown_legacy", "No declared immutable strategy template version in this legacy source.")
    strategy = {"record_type": "strategy", "id": "stock-signal", "label": "Stock Signal",
                "description": "Fixed deterministic strategy; saved comparison variants are descriptive labels.",
                "supported_modes": ["historical"], "editable_fields": [],
                "template_version": version, "strategy_version": version}
    bounds = ({"start": metadata["requested_start"], "end_exclusive": metadata["requested_end_exclusive"]}
              if metadata.get("requested_start") and metadata.get("requested_end_exclusive") else None)
    dataset = {"record_type": "dataset", "id": dataset_id, "label": scenario,
               "content_sha256": recorded(protocol, "dataset_file_sha256"), "feed": recorded(metadata, "feed"),
               "symbols": metadata.get("symbols", []), "requested_bounds": available(bounds) if bounds else unavailable(),
               "session_coverage": recorded(protocol, "coverage"), "synthetic": synthetic,
               "metadata_state": "partial", "approved_windows": [],
               "warmup_capability": unavailable("unverified", "Execution catalog approval is outside A1."),
               "availability": unavailable("unverified", "Saved metadata does not establish executable dataset availability.")}
    run = {"record_type": "normalized_run", "id": run_id, "strategy_id": "stock-signal", "strategy_version": version,
           "variant": row["variant"], "dataset_id": dataset_id, "dataset_sha256": recorded(protocol, "dataset_file_sha256"),
           "selected_data_sha256": recorded(manifest, "dataset_sha256"), "window": window,
           "observed_bounds": {"first_bar": recorded(manifest, "start"), "last_bar": recorded(manifest, "end"),
                               "warmup_end_exclusive": (available(datetime.fromisoformat(manifest["evaluation_start"].replace("Z", "+00:00")).isoformat())
                                                        if manifest.get("evaluation_start") else unavailable())},
           "symbols": manifest.get("symbols", []), "feed": recorded(manifest, "feed"),
           "cost_policy": dict(protocol["costs"], id=scenario, evidence="Declared modeled scenario; not measured quote/fill costs."),
           "accounting": accounting, "fill_policy": recorded(manifest, "fill_policy"), "session_policy": recorded(manifest, "session_policy"),
           "code": {key: recorded(manifest, key) for key in ("revision", "source_sha256", "working_diff_sha256")},
           "provenance": provenance}
    metrics = row["metrics"]
    realized_basis = "Realized closed trades; " + metrics["metric_basis"]
    prefix = "/comparison/" + str(row_index)
    values = {}
    for name, source_name, unit in (
        ("realized_net_pnl", "total_pnl", "USD"), ("gross_pnl", "gross_pnl", "USD"),
        ("recorded_costs", "costs", "USD"), ("closed_trades", "n_closed", "count"),
        ("realized_max_drawdown", "max_drawdown", "USD")):
        values[name] = metric(metrics.get(source_name), unit, realized_basis, prefix + "/metrics/" + source_name)
    values["censored_positions"] = metric(row.get("censored_positions"), "count", "Positions open at window end; not realized closes.", prefix + "/censored_positions")
    marked_values = marked.get("marked", {}) if marked else {}
    marked_basis = "Marked portfolio; " + marked_values.get("valuation_policy", "No saved marked valuation policy.")
    marked_basis += " Excludes dividend cash flows, short borrow fees and taxes."
    for name, source_name, unit in (
        ("marked_net_pnl", "marked_net_pnl", "USD"), ("marked_max_drawdown", "max_marked_drawdown", "USD"),
        ("marked_net_per_session", "marked_net_per_session", "USD/session"), ("max_gross_exposure", "max_gross_exposure", "USD")):
        values[name] = metric(marked_values.get(source_name), unit, marked_basis,
                              "/marked_review/" + str(marked_index) + "/marked/" + source_name,
                              unavailable("missing_artifact", "No saved marked review value in this fixture."))
    for name in ("borrow_cost", "dividend_cashflow", "spread_cost", "slippage_cost", "fees"):
        reason = "not_modeled" if name in ("borrow_cost", "dividend_cashflow") else "not_recorded"
        values[name] = metric(None, "USD", "No separate saved accounting amount; no zero imputation.", None,
                              unavailable(reason, "Absent from saved amount decomposition; a scenario rate is not a cost total."))
    by_regime = (available({"basis": realized_basis, "unit": "USD", "source_pointer": prefix + "/metrics/by_regime", "values": metrics["by_regime"]})
                 if "by_regime" in metrics else unavailable())
    limitations = list(dict.fromkeys(row.get("diagnostics", {}).get("limitations", []) + marked_values.get("limitations", []) +
                        ["Accounting incomplete: dividends, borrow, taxes and cost decomposition unresolved.",
                         "Synthetic correctness fixture; no strategy evidence." if synthetic else "Retrospective research; saved holdout role is not untouched evaluation."]))
    result = {"record_type": "result", "id": result_id, "run_id": run_id, "window": window, "variant": row["variant"],
              "provenance": provenance, "accounting": accounting, "metrics": values, "by_regime": by_regime,
              "limitations": limitations, "artifact_ids": []}
    status = {"record_type": "status", "run_id": run_id, "origin": "saved_artifact", "state": "completed",
              **{key: unavailable() for key in ("created_at", "started_at", "ended_at", "phase", "progress", "heartbeat_at", "attempt", "engine_run_id")},
              "result_id": available(result_id), "failure": unavailable("not_applicable", "No job failure record."),
              "cancellation": unavailable("not_applicable", "No cancellation record.")}
    return [envelope(item) for item in (strategy, dataset, run, result, status)]


def validate(records):
    Draft202012Validator.check_schema(SCHEMA)
    VALIDATOR.validate(records)
    for item in [records] if isinstance(records, dict) else records:
        data = item["data"]
        if "window" in data:
            window = data["window"]
            if datetime.fromisoformat(window["start"].replace("Z", "+00:00")) >= datetime.fromisoformat(window["end_exclusive"].replace("Z", "+00:00")):
                raise ValueError("Window start must precede its exclusive end")
        if data["record_type"] == "result":
            for name in ("borrow_cost", "dividend_cashflow"):
                if name in data["accounting"]["unresolved"] and data["metrics"][name]["observation"]["availability"] != "unavailable":
                    raise ValueError("Unresolved accounting amount cannot be presented as available: " + name)


def synthetic_records():
    fixture = json.loads((HERE / "fixtures/synthetic-source.json").read_text())
    if fixture["synthetic"] is not True:
        raise ValueError("Correctness fixture must explicitly be synthetic")
    return normalize(fixture["protocol"], fixture["comparison"][0], fixture["manifest"], None, "synthetic-contract-v1", True)


def check_saved(directory):
    """Read only known files in the two explicitly selected saved v2 comparisons."""
    directory = Path(directory)
    if directory.name not in ("alpaca-iex-2026-base-v2", "alpaca-iex-2026-adverse-v2"):
        raise ValueError("A1 harness accepts only the two reviewed v2 scenario directories")
    snapshots = {}

    def read(relative):
        path = directory / relative
        content = path.read_bytes()
        snapshots[path] = hashlib.sha256(content).hexdigest()
        return json.loads(content)

    protocol = read("protocol.json")
    comparisons = read("comparison.json")
    marked = read("marked-review.json")
    if len(comparisons) != 8 or len(marked) != 8:
        raise ValueError("Expected all eight window/variant rows per scenario")
    expected = {(window, variant) for window in ("development", "holdout") for variant in ("baseline", "strength", "rvol", "both")}
    if {(row["window"]["name"], row["variant"]) for row in comparisons} != expected:
        raise ValueError("Comparison rows do not match frozen windows/variants")
    marked_by_key = {(row["window"], row["variant"]): (index, row) for index, row in enumerate(marked)}
    if set(marked_by_key) != expected:
        raise ValueError("Marked rows do not match frozen windows/variants")
    for index, row in enumerate(comparisons):
        name, variant = row["window"]["name"], row["variant"]
        manifest = read(name + "/" + variant + "/manifest.json")
        saved_metrics = read(name + "/" + variant + "/metrics.json")
        saved_diagnostics = read(name + "/" + variant + "/diagnostics.json")
        if row["metrics"] != saved_metrics or row["diagnostics"] != saved_diagnostics:
            raise ValueError("Comparison does not match saved per-run values")
        digest = protocol["dataset_file_sha256"]
        if any(value != digest for value in (protocol["dataset_metadata"]["dataset_file_sha256"], manifest["input_dataset_sha256"], manifest["dataset_metadata"]["dataset_file_sha256"])):
            raise ValueError("Dataset identities disagree")
        if manifest["window"] != row["window"] or row["window"] not in protocol["windows"]:
            raise ValueError("Saved window definitions disagree")
        if manifest["gate"] != variant or manifest["source"] != "backtest" or manifest["backend"] != "local":
            raise ValueError("Unexpected saved provenance")
        for source, setting in (("spread_bps", "SPREAD_BPS"), ("slippage_bps_per_fill", "SLIPPAGE_BPS"), ("fee_per_share_per_fill", "FEE_PER_SHARE")):
            if protocol["costs"][source] != manifest["settings"][setting]:
                raise ValueError("Saved cost policies disagree")
        marked_index, marked_row = marked_by_key[(name, variant)]
        records = normalize(protocol, row, manifest, marked_row, directory.name, False, index, marked_index)
        result = records[3]["data"]
        for filename, kind in (("protocol.json", "protocol"), ("comparison.json", "comparison"), ("marked-review.json", "marked_review")):
            path = directory / filename
            artifact_id = identifier(result["id"] + ":" + kind)
            result["artifact_ids"].append(artifact_id)
            records.append(envelope({"record_type": "artifact", "id": artifact_id, "result_id": result["id"], "kind": kind,
                                     "sha256": snapshots[path], "mime_type": "application/json", "byte_size": path.stat().st_size}))
        validate(records)
    if any(hashlib.sha256(path.read_bytes()).hexdigest() != digest for path, digest in snapshots.items()):
        raise ValueError("Source bytes changed during validation")
    return {"scenario": directory.name, "validated_rows": len(comparisons), "unchanged_files": len(snapshots),
            "evaluation": "retrospective", "accounting": "incomplete"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saved", nargs="*", type=Path, default=[])
    args = parser.parse_args()
    validate(synthetic_records())
    print("Synthetic omission fixture: valid; explicitly synthetic, accounting incomplete.")
    for directory in args.saved:
        print(json.dumps(check_saved(directory), sort_keys=True))


if __name__ == "__main__":
    main()

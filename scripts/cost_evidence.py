"""Inventory saved execution-cost evidence without network or broker access.

The command only reads an existing research-output tree.  Replay trades are
reported as modeled fills; they are never promoted to broker-observed fills.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


QUOTE_MARKERS = ("quote", "nbbo", "book", "level1")
FILL_MARKERS = ("fill", "execution")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_count(path: Path) -> tuple[int | None, str | None]:
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        return None, f"unreadable_or_malformed_json:{type(exc).__name__}"
    if not isinstance(value, list):
        return None, "invalid_schema:expected_json_array"
    return len(value), None


def inventory(root: Path) -> dict:
    """Return a stable, credential-free inventory of local cost evidence."""
    if not root.exists():
        raise ValueError(f"inventory root does not exist: {root}")
    if not root.is_dir():
        raise ValueError(f"inventory root is not a directory: {root}")
    files = sorted(p for p in root.rglob("*") if p.is_file())
    quote_files = [p for p in files if any(m in p.name.lower() for m in QUOTE_MARKERS)]
    fill_files = [p for p in files if any(m in p.name.lower() for m in FILL_MARKERS)]
    activity_files = sorted(root.glob("**/account-activities.json"))
    trade_files = sorted(root.glob("**/trades.json"))
    run_db_files = sorted(root.glob("**/run.db"))
    modeled_trades = 0
    modeled_runs = 0
    exclusions = []
    modeled_trade_files = []
    for path in trade_files:
        manifest_path = path.parent / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, ValueError) as exc:
            manifest = {}
            exclusions.append({"path": manifest_path.relative_to(root).as_posix(), "reason": f"unreadable_or_malformed_json:{type(exc).__name__}"})
        if not isinstance(manifest, dict):
            exclusions.append({"path": manifest_path.relative_to(root).as_posix(), "reason": "invalid_schema:expected_json_object"})
            manifest = {}
        # A trade export is replay evidence only when its sibling manifest says
        # it is a local backtest.  Unknown/live artifacts stay out of the count.
        if manifest.get("source") != "backtest" or manifest.get("backend") != "local":
            exclusions.append({"path": path.relative_to(root).as_posix(), "reason": "excluded_unknown_or_non_replay_manifest"})
            continue
        rows, error = _json_count(path)
        if error:
            exclusions.append({"path": path.relative_to(root).as_posix(), "reason": error})
            continue
        if rows is None:
            continue
        modeled_trades += rows
        modeled_runs += 1
        modeled_trade_files.append(path)

    activity_rows = 0
    fill_activity_rows = 0
    activity_types: Counter[str] = Counter()
    activity_hashes = []
    for path in activity_files:
        try:
            rows = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            exclusions.append({"path": path.relative_to(root).as_posix(), "reason": f"unreadable_or_malformed_json:{type(exc).__name__}"})
            continue
        if not isinstance(rows, list):
            exclusions.append({"path": path.relative_to(root).as_posix(), "reason": "invalid_schema:expected_json_array"})
            continue
        activity_rows += len(rows)
        for row in rows:
            if not isinstance(row, dict):
                exclusions.append({"path": path.relative_to(root).as_posix(), "reason": "invalid_schema:activity_row_not_object"})
                continue
            activity_type = str(row.get("activity_type", "unknown"))
            activity_types.update([activity_type])
            if activity_type == "FILL":
                fill_activity_rows += 1
        activity_hashes.append({"path": path.relative_to(root).as_posix(), "sha256": _sha256(path)})

    sources = [
        {
            "source": "saved_quotes",
            "status": "missing" if not quote_files else "present_unparsed",
            "records": 0,
            "files": [p.relative_to(root).as_posix() for p in quote_files],
            "excluded_reason": "No quote or NBBO observations are saved; spread and quote age cannot be measured."
            if not quote_files else "Schema is not recognized by this inventory; exclude until fields are mapped.",
        },
        {
            "source": "broker_observed_fills",
            "status": "present_unparsed" if (fill_files or fill_activity_rows) else "missing",
            "records": fill_activity_rows,
            "files": [p.relative_to(root).as_posix() for p in fill_files],
            "excluded_reason": "FILL activities require schema mapping for timestamp, side, feed, quantity and price; excluded pending mapping."
            if (fill_files or fill_activity_rows) else "No saved fill/execution feed with timestamp, side, feed, quantity and price.",
        },
        {
            "source": "replay_modeled_fills",
            "status": "modeled_only",
            "records": modeled_trades,
            "runs": modeled_runs,
            "files": [p.relative_to(root).as_posix() for p in modeled_trade_files],
            "excluded_reason": "Replay prices and configured costs are scenario inputs, not execution evidence.",
        },
        {
            "source": "paper_account_activities",
            "status": "present_unparsed" if fill_activity_rows else ("present_non_fill" if activity_rows else "missing"),
            "records": activity_rows,
            "activity_types": dict(sorted(activity_types.items())),
            "files": activity_hashes,
            "excluded_reason": "FILL activity rows require execution-field mapping; other activities are not fills."
            if fill_activity_rows else "Account activity is not attributable execution evidence; no fill row is present.",
        },
        {
            "source": "run_db_journals",
            "status": "uninspected",
            "records": 0,
            "files": [p.relative_to(root).as_posix() for p in run_db_files],
            "excluded_reason": "SQLite journals were located but not parsed by this offline inventory; fill evidence remains unknown until schema-level inspection.",
        },
    ]
    return {
        "schema_version": 1,
        "root": root.name,
        "source_coverage": sources,
        "matching_fields_required": ["timestamp", "side", "feed", "quote_age", "quantity", "price"],
        "matching_policy": "A quote/fill pair is usable only when timestamp, side, feed and age are available; future observations are excluded.",
        "modeled_cost_warning": "Never deduct modeled spread or slippage again from an observed fill.",
        "cost_components": ["spread", "slippage", "commission", "borrow", "dividend"],
        "observed_quote_records": 0,
        "observed_fill_records": fill_activity_rows,
        "modeled_replay_records": modeled_trades,
        "status": "insufficient_observed_execution_evidence",
        "exclusions": exclusions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("research-output"))
    parser.add_argument("--output", type=Path, help="Write JSON here; stdout is unchanged")
    args = parser.parse_args()
    report = inventory(args.root)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()

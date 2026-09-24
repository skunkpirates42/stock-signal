"""Approved replay inputs and the trusted builder for historical demo run requests.

Browser requests name catalog IDs only. Dataset locations, cost values and windows come
from this module, never from a request, and every selection is recorded in an A1
``normalized_run`` record before any replay starts.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

import pandas as pd

import config
from backtest import manifest_for, normalize_bars
from data.sessions import utc
from db.logger import ACCOUNTING_VERSION

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_ID = "stock-signal"
TEMPLATE_VERSION = "stock-signal-template-1"
TRADER_WINDOW_BARS = 120
REQUEST_FIELDS = frozenset({"strategy_id", "dataset_id", "window_id", "cost_profile_id", "idempotency_key"})
IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9_-]{8,128}")
COST_SETTING_KEYS = frozenset({"SPREAD_BPS", "SLIPPAGE_BPS", "FEE_PER_SHARE"})
# Operational settings that cannot change a replay decision stay out of the strategy fingerprint.
NON_STRATEGY_SETTING_KEYS = frozenset({"BROKER", "DASHBOARD_PORT", "BACKTEST_BARS", "WATCHLIST"})


class ReplayRequestRejected(ValueError):
    """A run request that names unapproved inputs or cannot be replayed as approved."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CostProfile:
    id: str
    label: str
    spread_bps: float
    slippage_bps_per_fill: float
    fee_per_share_per_fill: float
    evidence: str

    def policy_record(self) -> Dict[str, Any]:
        return {"id": self.id, "spread_bps": self.spread_bps, "slippage_bps_per_fill": self.slippage_bps_per_fill,
                "fee_per_share_per_fill": self.fee_per_share_per_fill, "evidence": self.evidence}

    def child_environment(self) -> Dict[str, str]:
        return {"SPREAD_BPS": repr(self.spread_bps), "SLIPPAGE_BPS": repr(self.slippage_bps_per_fill),
                "FEE_PER_SHARE": repr(self.fee_per_share_per_fill)}


@dataclass(frozen=True)
class ApprovedWindow:
    id: str
    start: str
    end_exclusive: str


@dataclass(frozen=True)
class ApprovedDataset:
    id: str
    label: str
    relative_path: str
    sha256: str
    feed: str
    synthetic: bool
    windows: Tuple[ApprovedWindow, ...]
    cost_profile_ids: Tuple[str, ...]


COST_PROFILES = {
    profile.id: profile for profile in (
        CostProfile("base-v2", "Base modeled costs", 2.0, 1.0, 0.0,
                    "Declared scenario matching the saved base-v2 protocol; not measured spread."),
        CostProfile("adverse-v2", "Adverse modeled costs", 5.0, 2.0, 0.0,
                    "Declared scenario matching the saved adverse-v2 protocol; not measured spread."),
    )
}

DATASETS = {
    dataset.id: dataset for dataset in (
        ApprovedDataset(
            id="6f1d0a52-3c1b-4f7e-9a51-0c6a1f4e2b10", label="Synthetic seeded fixture (correctness only)",
            relative_path="tests/fixtures/bars.json",
            sha256="c79214e28a17c660c47aff560d142e0ec7e01dfb99f91f3a251e0b8855905464",
            feed="synthetic:seeded-fixture", synthetic=True,
            windows=(ApprovedWindow("fixture-day-2", "2026-06-10T13:30:00+00:00", "2026-06-10T20:00:00+00:00"),),
            cost_profile_ids=("base-v2", "adverse-v2"),
        ),
        ApprovedDataset(
            id="b8e4c7d2-51a9-4c36-8f0e-2d7a9e3c4b61", label="Alpaca IEX 5-minute bars, Jan-Aug 2026",
            relative_path="research-output/alpaca-iex-2026-jan-aug/bars.json",
            sha256="e0bcfc03a01af206f660e031567416750ea29cbbc8f2345fe834739a4b74c88e",
            feed="alpaca:iex", synthetic=False,
            windows=(ApprovedWindow("development", "2026-03-01T00:00:00+00:00", "2026-07-01T00:00:00+00:00"),
                     ApprovedWindow("holdout", "2026-07-01T00:00:00+00:00", "2026-09-01T00:00:00+00:00")),
            cost_profile_ids=("base-v2", "adverse-v2"),
        ),
    )
}


@dataclass(frozen=True)
class ReplayRequest:
    idempotency_key: str
    request_fingerprint: str
    normalized_run: Dict[str, Any]
    strategy_configuration: Dict[str, Any]
    cost_profile: CostProfile
    evaluation_start: pd.Timestamp
    bars: Dict[str, pd.DataFrame]


def _available(value: Any, detail: Optional[str] = None) -> Dict[str, Any]:
    return {"availability": "available", "value": value, "reason": None, "detail": detail}


def _unavailable(reason: str, detail: str) -> Dict[str, Any]:
    return {"availability": "unavailable", "value": None, "reason": reason, "detail": detail}


def _canonical_sha256(value: Any) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(serialized.encode()).hexdigest()


def dataset_is_available(dataset: ApprovedDataset, root: Path = ROOT) -> bool:
    path = root / dataset.relative_path
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == dataset.sha256


def request_fingerprint(request: Mapping[str, Any]) -> str:
    return _canonical_sha256({key: request[key] for key in sorted(REQUEST_FIELDS - {"idempotency_key"})})


def validated_request_fields(request: Any) -> Dict[str, str]:
    if not isinstance(request, Mapping):
        raise ReplayRequestRejected("invalid_request", "Run request must be a JSON object")
    unexpected = set(request) - REQUEST_FIELDS
    if unexpected:
        raise ReplayRequestRejected("unexpected_field", "Run request accepts catalog IDs only")
    missing = REQUEST_FIELDS - set(request)
    if missing:
        raise ReplayRequestRejected("missing_field", "Run request is missing a required catalog ID")
    if not all(isinstance(request[key], str) for key in REQUEST_FIELDS):
        raise ReplayRequestRejected("invalid_request", "Run request values must be strings")
    if not IDEMPOTENCY_KEY.fullmatch(request["idempotency_key"]):
        raise ReplayRequestRejected("invalid_idempotency_key", "Idempotency key must be 8-128 URL-safe characters")
    return dict(request)


def _recorded_feed(meta_path: Path) -> Optional[str]:
    try:
        meta = json.loads(meta_path.read_text())
    except (OSError, ValueError):
        return None
    return meta.get("feed") if isinstance(meta, dict) else None


def _load_verified_bars(dataset: ApprovedDataset, root: Path) -> Dict[str, pd.DataFrame]:
    path = root / dataset.relative_path
    if not path.is_file():
        raise ReplayRequestRejected("dataset_unavailable", "Approved dataset is not present on this host")
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ReplayRequestRejected("dataset_unavailable", "Approved dataset could not be read") from exc
    if hashlib.sha256(content).hexdigest() != dataset.sha256:
        raise ReplayRequestRejected("dataset_changed", "Approved dataset bytes do not match the catalog digest")
    if _recorded_feed(path.with_suffix(".meta.json")) != dataset.feed:
        raise ReplayRequestRejected("dataset_changed", "Dataset feed metadata does not match the catalog feed")
    return {symbol: normalize_bars(pd.DataFrame(rows)) for symbol, rows in json.loads(content).items()}


def _select_window(bars: Dict[str, pd.DataFrame], start: pd.Timestamp,
                   end: pd.Timestamp) -> Dict[str, pd.DataFrame]:
    selected = {}
    for symbol, frame in sorted(bars.items()):
        warmup = frame[frame.timestamp < start].tail(TRADER_WINDOW_BARS)
        evaluation = frame[(frame.timestamp >= start) & (frame.timestamp < end)]
        if evaluation.empty:
            raise ReplayRequestRejected("empty_window", "Approved window has no evaluation bars for a symbol")
        if len(warmup) < config.WARMUP_BARS:
            raise ReplayRequestRejected("insufficient_warmup",
                                        f"Window needs {config.WARMUP_BARS} warmup bars per symbol before its start")
        selected[symbol] = pd.concat([warmup, evaluation]).reset_index(drop=True)
    return selected


def _strategy_configuration(manifest: Dict[str, Any]) -> Dict[str, Any]:
    return {"template_version": TEMPLATE_VERSION, "source_sha256": manifest["source_sha256"],
            "configuration": {key: value for key, value in manifest["settings"].items()
                              if key not in COST_SETTING_KEYS | NON_STRATEGY_SETTING_KEYS}}


def strategy_version_for(strategy_configuration: Mapping[str, Any]) -> str:
    return _canonical_sha256({"template_version": strategy_configuration["template_version"],
                              "source_sha256": strategy_configuration["source_sha256"],
                              "configuration_sha256": _canonical_sha256(strategy_configuration["configuration"])})


def _provenance(dataset: ApprovedDataset) -> Dict[str, Any]:
    not_registered = _unavailable("not_registered", "No prospective registration exists for this replay window.")
    if dataset.synthetic:
        return {"source": "backtest", "execution": "local_simulation", "historical": True, "retrospective": False,
                "synthetic": True, "evaluation": "synthetic_correctness", "holdout_status": not_registered,
                "label_evidence": [f"replay catalog dataset {dataset.id} synthetic=true"]}
    return {"source": "backtest", "execution": "local_simulation", "historical": True, "retrospective": True,
            "synthetic": False, "evaluation": "retrospective", "holdout_status": not_registered,
            "label_evidence": [f"replay catalog dataset {dataset.id} covers already examined market data"]}


def build_replay_request(request: Any, *, root: Path = ROOT) -> ReplayRequest:
    fields = validated_request_fields(request)
    if fields["strategy_id"] != STRATEGY_ID:
        raise ReplayRequestRejected("unknown_strategy", "Strategy is not approved for replay")
    dataset = DATASETS.get(fields["dataset_id"])
    if dataset is None:
        raise ReplayRequestRejected("unknown_dataset", "Dataset is not approved for replay")
    window = next((item for item in dataset.windows if item.id == fields["window_id"]), None)
    if window is None:
        raise ReplayRequestRejected("unknown_window", "Window is not approved for this dataset")
    if fields["cost_profile_id"] not in dataset.cost_profile_ids:
        raise ReplayRequestRejected("unknown_cost_profile", "Cost profile is not approved for this dataset")
    cost_profile = COST_PROFILES[fields["cost_profile_id"]]

    start, end = utc(window.start), utc(window.end_exclusive)
    bars = _load_verified_bars(dataset, root)
    selected = _select_window(bars, start, end)
    manifest = manifest_for(selected, dataset.feed)
    strategy_configuration = _strategy_configuration(manifest)
    strategy_version = strategy_version_for(strategy_configuration)
    first_bar = min(frame.timestamp.iloc[0] for frame in selected.values())
    last_bar = max(frame.timestamp.iloc[-1] for frame in selected.values())

    normalized_run = {
        "record_type": "normalized_run", "id": str(uuid.uuid4()), "strategy_id": STRATEGY_ID,
        "strategy_version": _available(strategy_version, f"Template {TEMPLATE_VERSION} with source and configuration digests."),
        "variant": "baseline", "dataset_id": dataset.id,
        "dataset_sha256": _available(dataset.sha256, "Verified catalog file digest."),
        "selected_data_sha256": _available(manifest["dataset_sha256"], "Engine fingerprint of selected warmup and evaluation bars."),
        "window": {"name": window.id, "role": "evaluation", "start": start.isoformat(), "end_exclusive": end.isoformat()},
        "observed_bounds": {"first_bar": _available(first_bar.isoformat()), "last_bar": _available(last_bar.isoformat()),
                            "warmup_end_exclusive": _available(start.isoformat())},
        "symbols": sorted(selected), "feed": _available(dataset.feed),
        "cost_policy": cost_profile.policy_record(),
        "accounting": {"version": _available(str(ACCOUNTING_VERSION)), "mode": "cashflow_accounted",
                       "coverage": "incomplete", "unresolved": ["borrow_cost", "dividend_cashflow"]},
        "fill_policy": _available(manifest["fill_policy"]),
        "session_policy": _available(manifest["session_policy"]),
        "code": {"revision": _available(manifest["revision"]) if manifest["revision"] != "unknown"
                 else _unavailable("not_recorded", "Git revision was unavailable when the request was built."),
                 "source_sha256": _available(manifest["source_sha256"]),
                 "working_diff_sha256": _available(manifest["working_diff_sha256"],
                                                   "Digest of the working diff; a revision with a diff is not a clean build.")},
        "provenance": _provenance(dataset),
    }
    return ReplayRequest(idempotency_key=fields["idempotency_key"], request_fingerprint=request_fingerprint(fields),
                         normalized_run=normalized_run, strategy_configuration=strategy_configuration,
                         cost_profile=cost_profile, evaluation_start=start, bars=selected)

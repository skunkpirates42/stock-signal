"""Bounded, owner-scoped read models for the local engine-demo API.

This module deliberately reads only A2's public projections and indexed file
metadata.  It never exposes import metadata, source locations, or a filesystem
path, and it provides no import, replay, or mutation operation.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .artifacts import ArtifactImportError, ArtifactIndex, ImportedArtifact
from .availability import available, unavailable


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
MAX_JSON_RECORD_BYTES = 128 * 1024
MAX_JSON_RESPONSE_BYTES = 512 * 1024
MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_DETAIL_ARTIFACTS = 100


class DemoNotFound(LookupError):
    """The requested opaque resource is absent, inaccessible, or unsafe to serve."""


class DemoContentTooLarge(ValueError):
    """The indexed resource exceeds A3's deliberately small read limit."""


@dataclass(frozen=True)
class ArtifactReference:
    id: str
    result_id: str
    kind: str
    sha256: str
    mime_type: str
    byte_size: int

    def as_record(self) -> Dict[str, Any]:
        return {
            "record_type": "artifact",
            "id": self.id,
            "result_id": self.result_id,
            "kind": self.kind,
            "sha256": self.sha256,
            "mime_type": self.mime_type,
            "byte_size": self.byte_size,
        }


def envelope(data: Any, warnings: Iterable[str] = ()) -> Dict[str, Any]:
    """Return the fixed v1 outer envelope used by every JSON demo route."""
    return {"schema_version": 1, "data": data, "warnings": list(dict.fromkeys(warnings))}


class DemoReadService:
    """A read-only facade over an A2 index for one configured local operator."""

    def __init__(self, db_path: Path | str, *, owner_id: str = "local"):
        if not isinstance(owner_id, str) or not owner_id:
            raise ValueError("A configured demo owner is required")
        # A2 creates/migrates the local index once; this service has no write method.
        self.index = ArtifactIndex(db_path)
        self.owner_id = owner_id

    @staticmethod
    def _opaque_id(value: str) -> str:
        """Accept only canonical UUIDs, so route IDs can never be paths."""
        try:
            parsed = uuid.UUID(value)
        except (AttributeError, TypeError, ValueError) as exc:
            raise DemoNotFound("Unknown resource") from exc
        if str(parsed) != value:
            raise DemoNotFound("Unknown resource")
        return value

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.index.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _decode_record(raw: str) -> Dict[str, Any]:
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_JSON_RECORD_BYTES:
            raise DemoContentTooLarge("Indexed JSON record exceeds the demo response limit")
        try:
            value = json.loads(raw)
        except (TypeError, UnicodeError, json.JSONDecodeError) as exc:
            raise DemoNotFound("Stored public projection is invalid") from exc
        if not isinstance(value, dict):
            raise DemoNotFound("Stored public projection is invalid")
        return value

    @staticmethod
    def _limit(value: Optional[str]) -> int:
        if value is None:
            return DEFAULT_PAGE_SIZE
        try:
            limit = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("limit must be an integer") from exc
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValueError("limit must be between 1 and %d" % MAX_PAGE_SIZE)
        return limit

    def _artifact_rows(self, result_id: str, *, limit: int = MAX_DETAIL_ARTIFACTS) -> List[ArtifactReference]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, result_id, kind, sha256, mime_type, byte_size
                   FROM demo_artifact_files
                   WHERE result_id=? AND owner_id=? ORDER BY id LIMIT ?""",
                (result_id, self.owner_id, limit + 1),
            ).fetchall()
        if len(rows) > limit:
            raise DemoContentTooLarge("Too many indexed artifacts for one result")
        return [ArtifactReference(**dict(row)) for row in rows]

    def _result_row(self, result_id: str) -> sqlite3.Row:
        result_id = self._opaque_id(result_id)
        with self._connect() as conn:
            row = conn.execute(
                """SELECT id, run_id, result_json, run_json
                   FROM demo_artifact_results WHERE id=? AND owner_id=?""",
                (result_id, self.owner_id),
            ).fetchone()
        if row is None:
            raise DemoNotFound("Unknown result")
        return row

    def list_research(self, *, limit: Optional[str] = None, cursor: Optional[str] = None) -> Dict[str, Any]:
        page_size = self._limit(limit)
        cursor_id = self._opaque_id(cursor) if cursor is not None else None
        sql = """SELECT id, result_json FROM demo_artifact_results
                 WHERE owner_id=?"""
        params: List[Any] = [self.owner_id]
        if cursor_id is not None:
            sql += " AND id>?"
            params.append(cursor_id)
        sql += " ORDER BY id LIMIT ?"
        params.append(page_size + 1)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        has_more = len(rows) > page_size
        rows = rows[:page_size]
        results, warnings = [], [
            "Saved-source research catalog only; it does not authorize execution or replay."
        ]
        for row in rows:
            try:
                record = self._decode_record(row["result_json"])
            except DemoContentTooLarge:
                warnings.append("An oversized saved result was omitted from this response.")
                continue
            if record.get("record_type") != "result" or record.get("id") != row["id"]:
                warnings.append("An invalid saved result projection was omitted from this response.")
                continue
            results.append(record)
        data = {"results": results, "next_cursor": rows[-1]["id"] if has_more and rows else None}
        return envelope(data, warnings)

    def result_detail(self, result_id: str) -> Dict[str, Any]:
        row = self._result_row(result_id)
        result = self._decode_record(row["result_json"])
        run = self._decode_record(row["run_json"])
        if (result.get("record_type") != "result" or result.get("id") != row["id"]
                or run.get("record_type") != "normalized_run" or run.get("id") != row["run_id"]):
            raise DemoNotFound("Stored public projection is invalid")
        artifacts = [item.as_record() for item in self._artifact_rows(row["id"])]
        # A2 does not persist a separate status record.  Do not invent job timings or
        # execution evidence; this is only the A1 saved-artifact completed reference.
        status = {
            "record_type": "status", "run_id": row["run_id"], "origin": "saved_artifact",
            "state": "completed",
            "created_at": unavailable("not_recorded", "Saved artifacts do not record a lifecycle creation time."),
            "started_at": unavailable("not_recorded", "Saved artifacts do not record a lifecycle start time."),
            "ended_at": unavailable("not_recorded", "Saved artifacts do not record a lifecycle end time."),
            "phase": unavailable("not_recorded", "Saved artifacts do not record lifecycle phase."),
            "progress": unavailable("not_recorded", "Saved artifacts do not record lifecycle progress."),
            "heartbeat_at": unavailable("not_recorded", "Saved artifacts do not record lifecycle heartbeats."),
            "attempt": unavailable("not_recorded", "Saved artifacts do not record a lifecycle attempt."),
            "engine_run_id": unavailable("not_recorded", "Saved artifacts do not record an engine run ID."),
            "result_id": available(row["id"]),
            "failure": unavailable("not_applicable", "This saved artifact is a completed result reference, not a job failure."),
            "cancellation": unavailable("not_applicable", "This saved artifact is a completed result reference, not a cancellable job."),
        }
        return envelope(
            {"result": result, "run": run, "artifacts": artifacts, "status": status},
            ["Saved-source result only; no job execution or approval is implied."],
        )

    def artifact_content(self, result_id: str, artifact_id: str) -> ImportedArtifact:
        result_id, artifact_id = self._opaque_id(result_id), self._opaque_id(artifact_id)
        with self._connect() as conn:
            row = conn.execute(
                """SELECT id, byte_size FROM demo_artifact_files
                   WHERE id=? AND result_id=? AND owner_id=?""",
                (artifact_id, result_id, self.owner_id),
            ).fetchone()
        if row is None or row["byte_size"] < 0:
            raise DemoNotFound("Unknown artifact")
        if row["byte_size"] > MAX_ARTIFACT_BYTES:
            raise DemoContentTooLarge("Indexed artifact exceeds the demo content limit")
        try:
            artifact = self.index.resolve_artifact(artifact_id, owner_id=self.owner_id,
                                                   max_bytes=MAX_ARTIFACT_BYTES)
        except ArtifactImportError as exc:
            # Missing/tampered files intentionally look like any other absent artifact.
            raise DemoNotFound("Unknown artifact") from exc
        if artifact.result_id != result_id or artifact.byte_size > MAX_ARTIFACT_BYTES:
            raise DemoNotFound("Unknown artifact")
        if len(artifact.content) != artifact.byte_size or len(artifact.content) > MAX_ARTIFACT_BYTES:
            raise DemoNotFound("Unknown artifact")
        return artifact

    @staticmethod
    def strategy_catalog() -> Dict[str, Any]:
        strategy = {
            "record_type": "strategy", "id": "stock-signal", "label": "Stock Signal",
            "description": "Saved deterministic historical strategy template.",
            "supported_modes": ["historical"], "editable_fields": [],
            "template_version": unavailable("unknown_legacy", "Saved artifacts lack an immutable template version."),
            "strategy_version": unavailable("unknown_legacy", "Saved artifacts lack an immutable strategy fingerprint."),
        }
        return envelope([strategy], ["Descriptive saved-source catalog only; no strategy is approved for execution."])

    def dataset_catalog(self, *, limit: Optional[str] = None) -> Dict[str, Any]:
        page_size = self._limit(limit)
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT run_json FROM demo_artifact_results WHERE owner_id=?
                   ORDER BY id LIMIT ?""", (self.owner_id, page_size * 4),
            ).fetchall()
        datasets, seen = [], set()
        warnings = ["Saved-source catalog only; raw dataset bytes are not indexed or replayable."]
        for row in rows:
            try:
                run = self._decode_record(row["run_json"])
            except DemoContentTooLarge:
                warnings.append("An oversized saved dataset projection was omitted from this response.")
                continue
            dataset_id = run.get("dataset_id")
            if not isinstance(dataset_id, str) or dataset_id in seen:
                continue
            try:
                self._opaque_id(dataset_id)
            except DemoNotFound:
                warnings.append("An invalid saved dataset projection was omitted from this response.")
                continue
            seen.add(dataset_id)
            provenance = run.get("provenance")
            if not isinstance(provenance, dict) or not isinstance(provenance.get("synthetic"), bool):
                warnings.append("A saved dataset with missing provenance evidence was omitted from this response.")
                continue
            datasets.append({
                "record_type": "dataset", "id": dataset_id, "label": "Indexed saved-source dataset",
                "content_sha256": run.get("dataset_sha256", unavailable("not_recorded", "Dataset digest is absent.")),
                "feed": run.get("feed", unavailable("not_recorded", "Dataset feed is absent.")),
                "symbols": run.get("symbols", []),
                # The result evaluation window is not evidence of the original
                # dataset's requested bounds, so it must never be substituted here.
                "requested_bounds": unavailable("not_recorded", "Saved source does not record requested dataset bounds."),
                "session_coverage": unavailable("unverified", "Saved source does not provide verified full session coverage."),
                "synthetic": provenance["synthetic"],
                "metadata_state": "partial", "approved_windows": [],
                "warmup_capability": unavailable("not_recorded", "Saved source does not establish replay warmup capability."),
                "availability": unavailable("unverified", "Raw dataset bytes are intentionally excluded from the A2 index."),
            })
            if len(datasets) >= page_size:
                break
        if len(rows) == page_size * 4 and len(datasets) < page_size:
            warnings.append("Catalog scan was bounded before all distinct saved datasets could be inspected.")
        return envelope({"datasets": datasets}, warnings)

    def cost_profile_catalog(self, *, limit: Optional[str] = None) -> Dict[str, Any]:
        page_size = self._limit(limit)
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT run_json FROM demo_artifact_results WHERE owner_id=?
                   ORDER BY id LIMIT ?""", (self.owner_id, page_size * 4),
            ).fetchall()
        profiles, seen = [], set()
        warnings = ["Descriptive saved cost settings only; this endpoint does not approve replay inputs."]
        for row in rows:
            try:
                run = self._decode_record(row["run_json"])
            except DemoContentTooLarge:
                warnings.append("An oversized saved cost profile was omitted from this response.")
                continue
            policy = run.get("cost_policy")
            if not isinstance(policy, dict) or not isinstance(policy.get("id"), str):
                warnings.append("An incomplete saved cost profile was omitted from this response.")
                continue
            # A legacy descriptive ID alone is not a promise that its values are
            # immutable.  Keep divergent saved settings visible instead of merging
            # them into one apparent executable choice.
            fingerprint = json.dumps(policy, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            profiles.append({
                "id": policy["id"], "label": "Indexed saved cost policy",
                "saved_values": {key: policy.get(key) for key in (
                    "spread_bps", "slippage_bps_per_fill", "fee_per_share_per_fill", "evidence")},
                "catalog_kind": "saved_source_description",
            })
            if len(profiles) >= page_size:
                break
        if len(rows) == page_size * 4 and len(profiles) < page_size:
            warnings.append("Catalog scan was bounded before all distinct saved cost settings could be inspected.")
        return envelope({"cost_profiles": profiles}, warnings)

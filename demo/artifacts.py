"""Fail-closed, read-only index for saved engine-demo artifacts.

The index records source locations and hashes; it never copies, rewrites, or serves an
arbitrary file. Public callers receive opaque IDs and verified bytes, never a source
path that could be reopened after verification.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import stat
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple


ROOT_ARTIFACTS = {
    "protocol.json": ("protocol", "application/json"),
    "comparison.json": ("comparison", "application/json"),
    "marked-review.json": ("marked_review", "application/json"),
    "comparison.md": ("report", "text/markdown"),
    "registration.json": ("registration", "application/json"),
    "data-review.json": ("data_health", "application/json"),
}
RUN_ARTIFACTS = {
    "manifest.json": ("manifest", "application/json"),
    "metrics.json": ("metrics", "application/json"),
    "diagnostics.json": ("diagnostics", "application/json"),
    "trades.json": ("trades", "application/json"),
    "equity.json": ("equity", "application/json"),
    "accounting.json": ("accounting", "application/json"),
    "cashflows.json": ("cashflows", "application/json"),
    "report.txt": ("report", "text/plain"),
    "bars.meta.json": ("dataset_metadata", "application/json"),
}
REVIEWED_V2_PROTOCOLS = {
    # A1's non-synthetic normalization has reviewed January-August retrospective
    # evidence only for these immutable, local saved scenarios.
    "alpaca-iex-2026-base-v2": "e536286475efaebb453a44d0c58caeb4799559dac8379ee8b0d4e96fe3810e2e",
    "alpaca-iex-2026-adverse-v2": "f25b1543b848c1710eb13be17e832853a8194ed0a4cfaa69e7205b64a5f99b3c",
}


class ArtifactImportError(ValueError):
    """A saved artifact is unsafe, inconsistent, or no longer matches its index."""


@dataclass(frozen=True)
class ImportReport:
    import_id: str
    imported: bool
    result_ids: Tuple[str, ...]
    artifact_count: int
    source_manifest_sha256: str


@dataclass(frozen=True)
class ImportedArtifact:
    id: str
    result_id: str
    kind: str
    mime_type: str
    byte_size: int
    content: bytes


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_component(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value in (".", ".."):
        raise ArtifactImportError("Unsafe %s component" % field)
    if "/" in value or "\\" in value or PurePosixPath(value).name != value:
        raise ArtifactImportError("Unsafe %s component" % field)
    return value


def _relative_parts(relative: str) -> Tuple[str, ...]:
    parts = tuple(PurePosixPath(relative).parts)
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ArtifactImportError("Unsafe artifact path: " + relative)
    return parts


@contextmanager
def _open_root(root: Path):
    """Open the source directory without following its final symlink."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(root), flags)
    except OSError as exc:
        raise ArtifactImportError("Artifact directory must be a real directory") from exc
    try:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise ArtifactImportError("Artifact directory must be a real directory")
        yield fd
    finally:
        os.close(fd)


def _read_file(root_fd: int, relative: str, required: bool = False,
               max_bytes: Optional[int] = None) -> Optional[Tuple[bytes, str]]:
    """Read a regular source file through no-follow, descriptor-relative traversal."""
    if max_bytes is not None and (isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 0):
        raise ValueError("max_bytes must be a nonnegative integer or None")
    parts = _relative_parts(relative)
    parent_fd = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            try:
                child_fd = os.open(part, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                                   getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
            except FileNotFoundError:
                if required:
                    raise ArtifactImportError("Missing required artifact: " + relative)
                return None
            except OSError as exc:
                raise ArtifactImportError("Unsafe artifact path: " + relative) from exc
            os.close(parent_fd)
            parent_fd = child_fd
        try:
            file_fd = os.open(parts[-1], os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) |
                              getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
        except FileNotFoundError:
            if required:
                raise ArtifactImportError("Missing required artifact: " + relative)
            return None
        except OSError as exc:
            raise ArtifactImportError("Unsafe artifact path: " + relative) from exc
        try:
            file_stat = os.fstat(file_fd)
            if not stat.S_ISREG(file_stat.st_mode):
                raise ArtifactImportError("Unsafe artifact path: " + relative)
            if max_bytes is not None and file_stat.st_size > max_bytes:
                raise ArtifactImportError("Indexed artifact exceeds maximum byte size")
            chunks = []
            total = 0
            while True:
                # The stat check is a fast path, but a file can grow after it.  Read
                # at most one byte beyond the ceiling so a stale index cannot make a
                # browser request consume an arbitrarily large source file.
                read_size = 1024 * 1024 if max_bytes is None else min(1024 * 1024, max_bytes - total + 1)
                chunk = os.read(file_fd, read_size)
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if max_bytes is not None and total > max_bytes:
                    raise ArtifactImportError("Indexed artifact exceeds maximum byte size")
            content = b"".join(chunks)
        except OSError as exc:
            raise ArtifactImportError("Cannot read indexed artifact: " + relative) from exc
        finally:
            os.close(file_fd)
        return content, _sha256(content)
    finally:
        os.close(parent_fd)


def _read_json(root_fd: int, relative: str, required: bool = False) -> Optional[Tuple[Any, bytes, str]]:
    item = _read_file(root_fd, relative, required)
    if item is None:
        return None
    content, digest = item
    try:
        return json.loads(content), content, digest
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactImportError("Invalid JSON artifact: " + relative) from exc


class _SourceSnapshot:
    """One import-time byte snapshot, parsed and fingerprinted from the same reads."""

    def __init__(self, root_fd: int):
        self.root_fd = root_fd
        self.files: Dict[str, Optional[Tuple[bytes, str]]] = {}
        self.json_values: Dict[str, Any] = {}

    def file(self, relative: str, required: bool = False) -> Optional[Tuple[bytes, str]]:
        if relative not in self.files:
            self.files[relative] = _read_file(self.root_fd, relative, required)
        item = self.files[relative]
        if item is None and required:
            raise ArtifactImportError("Missing required artifact: " + relative)
        return item

    def json(self, relative: str, required: bool = False) -> Optional[Tuple[Any, bytes, str]]:
        item = self.file(relative, required)
        if item is None:
            return None
        content, digest = item
        if relative not in self.json_values:
            try:
                self.json_values[relative] = json.loads(content)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ArtifactImportError("Invalid JSON artifact: " + relative) from exc
        return self.json_values[relative], content, digest

    def verify_unchanged(self) -> None:
        for relative, expected in self.files.items():
            if expected is None:
                continue
            current = _read_file(self.root_fd, relative, required=True)
            if current != expected:
                raise ArtifactImportError("Source artifacts changed during import")


class ArtifactIndex:
    """SQLite-backed registry for an explicitly allowlisted artifact tree."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS demo_artifact_imports (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    source_directory TEXT NOT NULL UNIQUE,
                    scenario_name TEXT NOT NULL,
                    protocol_sha256 TEXT NOT NULL,
                    source_manifest_sha256 TEXT NOT NULL,
                    projection_sha256 TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    UNIQUE(owner_id, source_manifest_sha256)
                );
                CREATE TABLE IF NOT EXISTS demo_artifact_results (
                    id TEXT PRIMARY KEY,
                    import_id TEXT NOT NULL REFERENCES demo_artifact_imports(id),
                    owner_id TEXT NOT NULL,
                    run_id TEXT NOT NULL UNIQUE,
                    window_name TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    run_json TEXT NOT NULL,
                    UNIQUE(import_id, window_name, variant)
                );
                CREATE TABLE IF NOT EXISTS demo_artifact_files (
                    id TEXT PRIMARY KEY,
                    import_id TEXT NOT NULL REFERENCES demo_artifact_imports(id),
                    result_id TEXT NOT NULL REFERENCES demo_artifact_results(id),
                    owner_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    byte_size INTEGER NOT NULL,
                    UNIQUE(import_id, result_id, relative_path)
                );
                CREATE INDEX IF NOT EXISTS demo_artifact_result_owner
                    ON demo_artifact_results(owner_id, id);
                CREATE INDEX IF NOT EXISTS demo_artifact_file_owner
                    ON demo_artifact_files(owner_id, id);
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(demo_artifact_imports)")}
            if "projection_sha256" not in columns:
                conn.execute("ALTER TABLE demo_artifact_imports ADD COLUMN projection_sha256 TEXT NOT NULL DEFAULT ''")

    def import_directory(self, directory: Path | str, *, owner_id: str = "local", synthetic: bool = False) -> ImportReport:
        """Validate and index a frozen directory without modifying its contents.

        ``owner_id`` is deliberately part of idempotency.  The same evidence cannot
        become visible to another owner simply because it has the same bytes.
        """
        if not isinstance(owner_id, str) or not owner_id:
            raise ArtifactImportError("owner_id is required")
        if not isinstance(synthetic, bool):
            raise ArtifactImportError("synthetic must be an explicit boolean label")
        root = Path(os.path.abspath(str(directory)))
        try:
            candidate = self._collect(root, synthetic)
        except ArtifactImportError:
            raise
        except (AttributeError, IndexError, KeyError, TypeError, UnicodeError, ValueError) as exc:
            raise ArtifactImportError("Malformed source artifact") from exc
        manifest_digest = candidate["source_manifest_sha256"]

        with self._connect() as conn:
            prior_source = conn.execute(
                "SELECT * FROM demo_artifact_imports WHERE source_directory=?", (str(root),)
            ).fetchone()
            if prior_source:
                if prior_source["owner_id"] != owner_id:
                    raise ArtifactImportError("Artifact directory is indexed for a different owner")
                if prior_source["source_manifest_sha256"] != manifest_digest:
                    raise ArtifactImportError("Indexed source artifacts changed; refusing replacement")
                if prior_source["projection_sha256"] != candidate["projection_sha256"]:
                    raise ArtifactImportError("Import labels would change the indexed public projection")
                return self._prior_report(conn, prior_source)

            prior_manifest = conn.execute(
                "SELECT * FROM demo_artifact_imports WHERE owner_id=? AND source_manifest_sha256=?",
                (owner_id, manifest_digest),
            ).fetchone()
            if prior_manifest:
                if prior_manifest["projection_sha256"] != candidate["projection_sha256"]:
                    raise ArtifactImportError("Import labels would change the indexed public projection")
                raise ArtifactImportError("Artifact content is already indexed from a different source directory")
            cross_owner = conn.execute(
                "SELECT 1 FROM demo_artifact_imports WHERE source_manifest_sha256=?", (manifest_digest,)
            ).fetchone()
            if cross_owner:
                raise ArtifactImportError("Artifact content is already indexed for a different owner")

            import_id = str(uuid.uuid4())
            dataset_id = str(uuid.uuid4())
            try:
                prepared = self._prepare_public_records(candidate, import_id, dataset_id, owner_id, synthetic)
                self._validate_public_records(prepared)
            except ArtifactImportError:
                raise
            except (AttributeError, IndexError, KeyError, TypeError, UnicodeError, ValueError) as exc:
                raise ArtifactImportError("Malformed source artifact") from exc
            conn.execute(
                """INSERT INTO demo_artifact_imports
                   (id, owner_id, source_directory, scenario_name, protocol_sha256,
                    source_manifest_sha256, projection_sha256, metadata_json, imported_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (import_id, owner_id, str(root), root.name, candidate["protocol_sha256"], manifest_digest,
                 candidate["projection_sha256"], candidate["metadata_json"], _utcnow()),
            )
            for result in prepared["results"]:
                conn.execute(
                    "INSERT INTO demo_artifact_results VALUES (?,?,?,?,?,?,?,?)",
                    (result["id"], import_id, owner_id, result["run_id"], result["window_name"],
                     result["variant"], result["result_json"], result["run_json"]),
                )
            for artifact in prepared["artifacts"]:
                conn.execute(
                    "INSERT INTO demo_artifact_files VALUES (?,?,?,?,?,?,?,?,?)",
                    (artifact["id"], import_id, artifact["result_id"], owner_id, artifact["kind"],
                     artifact["relative_path"], artifact["sha256"], artifact["mime_type"], artifact["byte_size"]),
                )
        return ImportReport(import_id, True, tuple(item["id"] for item in prepared["results"]),
                            len(prepared["artifacts"]), manifest_digest)

    def _prior_report(self, conn: sqlite3.Connection, imported: sqlite3.Row) -> ImportReport:
        results = conn.execute(
            "SELECT id FROM demo_artifact_results WHERE import_id=? ORDER BY window_name, variant", (imported["id"],)
        ).fetchall()
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM demo_artifact_files WHERE import_id=?", (imported["id"],)
        ).fetchone()["count"]
        return ImportReport(imported["id"], False, tuple(row["id"] for row in results), count,
                            imported["source_manifest_sha256"])

    def _collect(self, root: Path, synthetic: bool) -> Dict[str, Any]:
        with _open_root(root) as root_fd:
            snapshot = _SourceSnapshot(root_fd)
            return self._collect_snapshot(root, snapshot, synthetic)

    def _collect_snapshot(self, root: Path, snapshot: _SourceSnapshot, synthetic: bool) -> Dict[str, Any]:
        protocol_item = snapshot.json("protocol.json", required=True)
        comparison_item = snapshot.json("comparison.json", required=True)
        assert protocol_item and comparison_item
        protocol, protocol_bytes, protocol_digest = protocol_item
        comparison, _, _ = comparison_item
        if not isinstance(protocol, dict) or not isinstance(comparison, list) or not comparison:
            raise ArtifactImportError("protocol.json must be an object and comparison.json a nonempty array")
        if not isinstance(protocol.get("windows"), list) or not isinstance(protocol.get("costs"), dict):
            raise ArtifactImportError("Protocol lacks frozen windows or cost settings")
        if "dataset_metadata" in protocol and not isinstance(protocol["dataset_metadata"], dict):
            raise ArtifactImportError("Protocol dataset metadata must be an object")

        files: List[Dict[str, Any]] = []
        parsed: Dict[str, Any] = {"protocol.json": protocol, "comparison.json": comparison}
        for relative, (kind, mime_type) in ROOT_ARTIFACTS.items():
            item = snapshot.file(relative)
            if item is None:
                continue
            content, digest = item
            if mime_type == "application/json":
                parsed_item = snapshot.json(relative, required=True)
                assert parsed_item
                parsed[relative] = parsed_item[0]
            files.append({"relative_path": relative, "kind": kind, "mime_type": mime_type,
                          "sha256": digest, "byte_size": len(content), "result_key": None})

        marked = parsed.get("marked-review.json")
        if marked is not None and not isinstance(marked, list):
            raise ArtifactImportError("marked-review.json must be an array")
        marked_by_key = self._marked_rows(marked)
        rows = []
        for index, row in enumerate(comparison):
            if not isinstance(row, dict) or not isinstance(row.get("window"), dict):
                raise ArtifactImportError("Comparison row lacks a window")
            window = _safe_component(row["window"].get("name"), "window")
            variant = _safe_component(row.get("variant"), "variant")
            if not isinstance(row.get("metrics"), dict) or not isinstance(row.get("diagnostics"), dict):
                raise ArtifactImportError("Comparison row lacks saved metrics or diagnostics")
            if row["window"] not in protocol["windows"]:
                raise ArtifactImportError("Comparison window is not in protocol")
            key = (window, variant)
            run_files = {}
            for filename in ("manifest.json", "metrics.json", "diagnostics.json"):
                relative = "/".join((window, variant, filename))
                item = snapshot.json(relative, required=True)
                assert item
                run_files[filename] = item[0]
            manifest = run_files["manifest.json"]
            if not isinstance(manifest, dict) or manifest.get("window") != row["window"] or manifest.get("gate") != variant:
                raise ArtifactImportError("Run manifest does not match comparison row: %s/%s" % key)
            if "dataset_metadata" in manifest and not isinstance(manifest["dataset_metadata"], dict):
                raise ArtifactImportError("Run manifest dataset metadata must be an object")
            if run_files["metrics.json"] != row["metrics"] or run_files["diagnostics.json"] != row["diagnostics"]:
                raise ArtifactImportError("Comparison values do not match per-run artifacts: %s/%s" % key)
            self._verify_dataset_identity(protocol, manifest)
            self._verify_manifest_settings(protocol, manifest)
            for filename, (kind, mime_type) in RUN_ARTIFACTS.items():
                relative = "/".join((window, variant, filename))
                item = snapshot.file(relative, required=filename in ("manifest.json", "metrics.json", "diagnostics.json"))
                if item is None:
                    continue
                content, digest = item
                if mime_type == "application/json":
                    parsed_item = snapshot.json(relative, required=True)
                    assert parsed_item
                    parsed[relative] = parsed_item[0]
                files.append({"relative_path": relative, "kind": kind, "mime_type": mime_type,
                              "sha256": digest, "byte_size": len(content), "result_key": key})
            rows.append({"row": row, "index": index, "window": window, "variant": variant,
                         "manifest": manifest, "marked": marked_by_key.get(key)})

        provenance_evidence = self._verify_provenance(root.name, protocol_digest, protocol, rows, synthetic)
        # The parsed values, hashes and projected records all come from this snapshot.
        # Reopening every indexed path through the same no-follow traversal detects any
        # replacement before SQLite receives an immutable index entry.
        snapshot.verify_unchanged()
        fingerprint = json.dumps(
            [{"path": item["relative_path"], "sha256": item["sha256"], "byte_size": item["byte_size"]}
             for item in sorted(files, key=lambda item: item["relative_path"])],
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
        try:
            metadata_json = json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                      allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ArtifactImportError("Source metadata contains unsupported JSON values") from exc
        projection_sha256 = _sha256(json.dumps(
            {"synthetic": synthetic, "provenance_evidence": provenance_evidence},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
        ).encode("utf-8"))
        return {"protocol": protocol, "protocol_sha256": _sha256(protocol_bytes), "rows": rows, "files": files,
                "source_manifest_sha256": _sha256(fingerprint), "projection_sha256": projection_sha256,
                "metadata_json": metadata_json}

    @staticmethod
    def _marked_rows(marked: Any) -> Dict[Tuple[str, str], Tuple[int, Dict[str, Any]]]:
        if marked is None:
            return {}
        rows = {}
        for index, row in enumerate(marked):
            if not isinstance(row, dict):
                raise ArtifactImportError("Invalid marked review row")
            key = (_safe_component(row.get("window"), "marked-review window"),
                   _safe_component(row.get("variant"), "marked-review variant"))
            if key in rows:
                raise ArtifactImportError("Duplicate marked review row")
            rows[key] = (index, row)
        return rows

    @staticmethod
    def _verify_dataset_identity(protocol: Dict[str, Any], manifest: Dict[str, Any]) -> None:
        # These are declarations from legacy artifacts, not a claim that the raw bars
        # (which are intentionally never indexed) were available to hash here.
        declared = protocol.get("dataset_file_sha256")
        values = [declared, protocol.get("dataset_metadata", {}).get("dataset_file_sha256"),
                  manifest.get("input_dataset_sha256"), manifest.get("dataset_metadata", {}).get("dataset_file_sha256")]
        known = [value for value in values if value is not None]
        valid_digest = re.compile(r"^[0-9a-f]{64}$")
        if known and (not all(isinstance(value, str) and valid_digest.fullmatch(value) for value in known)
                      or len(set(known)) != 1):
            raise ArtifactImportError("Declared dataset identities disagree")

    @staticmethod
    def _verify_manifest_settings(protocol: Dict[str, Any], manifest: Dict[str, Any]) -> None:
        settings = manifest.get("settings")
        if not isinstance(settings, dict):
            raise ArtifactImportError("Run manifest lacks frozen cost settings")
        for protocol_key, manifest_key in (
            ("spread_bps", "SPREAD_BPS"),
            ("slippage_bps_per_fill", "SLIPPAGE_BPS"),
            ("fee_per_share_per_fill", "FEE_PER_SHARE"),
        ):
            protocol_value = protocol["costs"].get(protocol_key)
            manifest_value = settings.get(manifest_key)
            if (isinstance(protocol_value, bool) or isinstance(manifest_value, bool)
                    or not isinstance(protocol_value, (int, float))
                    or not isinstance(manifest_value, (int, float))
                    or protocol_value != manifest_value):
                raise ArtifactImportError("Protocol costs disagree with run manifest settings")

    @staticmethod
    def _verify_provenance(scenario_name: str, protocol_sha256: str, protocol: Dict[str, Any],
                           rows: List[Dict[str, Any]], synthetic: bool) -> Dict[str, str]:
        for source in rows:
            manifest = source["manifest"]
            if manifest.get("source") != "backtest" or manifest.get("backend") != "local":
                raise ArtifactImportError("Saved artifact provenance must be backtest/local")
        if synthetic:
            if protocol.get("synthetic") is not True:
                raise ArtifactImportError("Synthetic import requires an explicit source synthetic declaration")
            return {"mode": "synthetic", "source": "protocol.synthetic=true"}
        if protocol.get("synthetic") is True:
            raise ArtifactImportError("Source declares synthetic evidence; import must retain that label")
        expected = REVIEWED_V2_PROTOCOLS.get(scenario_name)
        if expected != protocol_sha256:
            raise ArtifactImportError("Retrospective projection is restricted to reviewed v2 source evidence")
        return {"mode": "retrospective", "source": "reviewed-v2:" + scenario_name}

    def _prepare_public_records(self, candidate: Dict[str, Any], import_id: str, dataset_id: str,
                                owner_id: str, synthetic: bool) -> Dict[str, Any]:
        contract = self._contract_module()
        results = []
        artifact_rows = []
        files_by_key: Dict[Optional[Tuple[str, str]], List[Dict[str, Any]]] = {}
        for item in candidate["files"]:
            files_by_key.setdefault(item["result_key"], []).append(item)
        root_files = files_by_key.get(None, [])
        for source in candidate["rows"]:
            run_id, result_id = str(uuid.uuid4()), str(uuid.uuid4())
            marked_index, marked_row = source["marked"] if source["marked"] else (0, None)
            records = contract.normalize(candidate["protocol"], source["row"], source["manifest"], marked_row,
                                         candidate["protocol"].get("label", import_id), synthetic,
                                         source["index"], marked_index)
            if synthetic:
                for envelope in records:
                    provenance = envelope["data"].get("provenance")
                    if provenance is not None:
                        provenance["label_evidence"] = ["protocol.synthetic=true"]
            for envelope in records:
                data = envelope["data"]
                if data["record_type"] == "dataset":
                    data["id"] = dataset_id
                elif data["record_type"] == "normalized_run":
                    data.update(id=run_id, dataset_id=dataset_id)
                elif data["record_type"] == "result":
                    data.update(id=result_id, run_id=run_id, artifact_ids=[])
                elif data["record_type"] == "status":
                    data.update(run_id=run_id, result_id=contract.available(result_id))
            result_data = next(item["data"] for item in records if item["data"]["record_type"] == "result")
            run_data = next(item["data"] for item in records if item["data"]["record_type"] == "normalized_run")
            scoped_files = root_files + files_by_key.get((source["window"], source["variant"]), [])
            for file in scoped_files:
                artifact_id = str(uuid.uuid4())
                result_data["artifact_ids"].append(artifact_id)
                records.append(contract.envelope({"record_type": "artifact", "id": artifact_id, "result_id": result_id,
                                                  "kind": file["kind"], "sha256": file["sha256"],
                                                  "mime_type": file["mime_type"], "byte_size": file["byte_size"]}))
                artifact_rows.append({**file, "id": artifact_id, "result_id": result_id})
            results.append({"id": result_id, "run_id": run_id, "window_name": source["window"],
                            "variant": source["variant"], "result_json": json.dumps(result_data, sort_keys=True,
                            separators=(",", ":"), ensure_ascii=False, allow_nan=False),
                            "run_json": json.dumps(run_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                            allow_nan=False), "records": records})
        return {"results": results, "artifacts": artifact_rows}

    @staticmethod
    def _contract_module():
        here = Path(__file__).resolve().parents[1]
        path = here / "docs" / "engine-demo" / "validate.py"
        spec = importlib.util.spec_from_file_location("demo_a1_contract", path)
        if spec is None or spec.loader is None:
            raise ArtifactImportError("Bundled A1 contract validator is unavailable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _validate_public_records(prepared: Dict[str, Any]) -> None:
        contract = ArtifactIndex._contract_module()
        for result in prepared["results"]:
            try:
                contract.validate(result["records"])
            except Exception as exc:
                raise ArtifactImportError("Artifact projection fails the A1 schema") from exc

    def resolve_artifact(self, artifact_id: str, *, owner_id: str = "local",
                         max_bytes: Optional[int] = None) -> ImportedArtifact:
        """Return verified bytes for an opaque indexed artifact ID only.

        Returning bytes rather than a source path prevents a later caller from opening
        a file after it changes between checksum verification and use.
        """
        if max_bytes is not None and (isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 0):
            raise ValueError("max_bytes must be a nonnegative integer or None")
        with self._connect() as conn:
            row = conn.execute(
                """SELECT files.*, imports.source_directory FROM demo_artifact_files AS files
                   JOIN demo_artifact_imports AS imports ON imports.id=files.import_id
                   WHERE files.id=? AND files.owner_id=?""", (artifact_id, owner_id),
            ).fetchone()
        if row is None:
            raise ArtifactImportError("Unknown artifact")
        if max_bytes is not None and row["byte_size"] > max_bytes:
            raise ArtifactImportError("Indexed artifact exceeds maximum byte size")
        root = Path(row["source_directory"])
        try:
            with _open_root(root) as root_fd:
                item = _read_file(root_fd, row["relative_path"], required=True, max_bytes=max_bytes)
                assert item
                content, digest = item
        except ArtifactImportError as exc:
            if str(exc) == "Indexed artifact exceeds maximum byte size":
                raise
            raise ArtifactImportError("Indexed source directory is unavailable") from exc
        if digest != row["sha256"] or len(content) != row["byte_size"]:
            raise ArtifactImportError("Indexed artifact no longer matches its checksum")
        return ImportedArtifact(row["id"], row["result_id"], row["kind"], row["mime_type"], row["byte_size"], content)

"""Offline A2 artifact-index checks using a small, synthetic legacy-shaped tree."""
import copy
import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from demo import artifacts
from demo.artifacts import ArtifactImportError, ArtifactIndex


ROOT = Path(__file__).resolve().parents[1]


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))


def artifact_tree(tmp_path):
    fixture = json.loads((ROOT / "docs/engine-demo/fixtures/synthetic-source.json").read_text())
    source = tmp_path / "synthetic-result"
    protocol = copy.deepcopy(fixture["protocol"])
    digest = "a" * 64
    protocol.update(synthetic=True, dataset_file_sha256=digest,
                    unprojected_protocol_field={"keep": ["unknown", "source", "data"]})
    protocol["dataset_metadata"]["dataset_file_sha256"] = digest
    row = copy.deepcopy(fixture["comparison"][0])
    manifest = copy.deepcopy(fixture["manifest"])
    manifest.update(window=row["window"], gate=row["variant"], input_dataset_sha256=digest,
                    dataset_metadata={"dataset_file_sha256": digest},
                    settings={"SPREAD_BPS": 2.0, "SLIPPAGE_BPS": 1.0, "FEE_PER_SHARE": 0.0},
                    unprojected_manifest_field="preserved internally")
    _write_json(source / "protocol.json", protocol)
    _write_json(source / "comparison.json", [row])
    _write_json(source / "fixture/baseline/manifest.json", manifest)
    _write_json(source / "fixture/baseline/metrics.json", row["metrics"])
    _write_json(source / "fixture/baseline/diagnostics.json", row["diagnostics"])
    # These must remain excluded even when present next to allowed result files.
    (source / "fixture/baseline/bars.json").write_text("raw bars must not be indexed")
    (source / "fixture/baseline/run.db").write_bytes(b"not a browser artifact")
    return source


def _artifact_id(db_path):
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT id FROM demo_artifact_files WHERE kind='metrics'").fetchone()[0]


def test_valid_import_is_idempotent_preserves_unknown_metadata_and_excludes_raw_files(tmp_path):
    source = artifact_tree(tmp_path)
    db = tmp_path / "demo.db"
    index = ArtifactIndex(db)
    original_hashes = {path.relative_to(source): hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in source.rglob("*") if path.is_file()}

    first = index.import_directory(source, synthetic=True)
    second = index.import_directory(source, synthetic=True)

    assert first.imported is True
    assert second.imported is False
    assert second.import_id == first.import_id
    assert len(first.result_ids) == 1
    artifact = index.resolve_artifact(_artifact_id(db))
    assert artifact.content == (source / "fixture/baseline/metrics.json").read_bytes()
    with sqlite3.connect(db) as conn:
        metadata = json.loads(conn.execute("SELECT metadata_json FROM demo_artifact_imports").fetchone()[0])
        paths = {row[0] for row in conn.execute("SELECT relative_path FROM demo_artifact_files")}
    assert metadata["protocol.json"]["unprojected_protocol_field"]["keep"] == ["unknown", "source", "data"]
    assert metadata["fixture/baseline/manifest.json"]["unprojected_manifest_field"] == "preserved internally"
    assert "fixture/baseline/bars.json" not in paths
    assert "fixture/baseline/run.db" not in paths
    assert {path.relative_to(source): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source.rglob("*") if path.is_file()} == original_hashes


def test_synthetic_projection_uses_explicit_source_evidence(tmp_path):
    source = artifact_tree(tmp_path)
    db = tmp_path / "demo.db"
    ArtifactIndex(db).import_directory(source, synthetic=True)

    with sqlite3.connect(db) as conn:
        result_json, run_json = conn.execute(
            "SELECT result_json, run_json FROM demo_artifact_results"
        ).fetchone()
    assert json.loads(result_json)["provenance"]["label_evidence"] == ["protocol.synthetic=true"]
    assert json.loads(run_json)["provenance"]["label_evidence"] == ["protocol.synthetic=true"]


def test_tampered_source_fails_on_resolution_and_reimport(tmp_path):
    source = artifact_tree(tmp_path)
    db = tmp_path / "demo.db"
    index = ArtifactIndex(db)
    index.import_directory(source, synthetic=True)
    artifact_id = _artifact_id(db)
    (source / "fixture/baseline/metrics.json").write_text('{"tampered": true}')

    with pytest.raises(ArtifactImportError, match="checksum"):
        index.resolve_artifact(artifact_id)
    with pytest.raises(ArtifactImportError):
        index.import_directory(source, synthetic=True)


def test_unsafe_window_component_is_rejected_before_any_path_resolution(tmp_path):
    source = artifact_tree(tmp_path)
    comparison_path = source / "comparison.json"
    rows = json.loads(comparison_path.read_text())
    rows[0]["window"]["name"] = "../outside"
    _write_json(comparison_path, rows)

    with pytest.raises(ArtifactImportError, match="Unsafe window"):
        ArtifactIndex(tmp_path / "demo.db").import_directory(source, synthetic=True)


def test_symlinked_allowed_filename_is_rejected(tmp_path):
    source = artifact_tree(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    metrics = source / "fixture/baseline/metrics.json"
    metrics.unlink()
    metrics.symlink_to(outside)

    with pytest.raises(ArtifactImportError, match="Unsafe artifact path"):
        ArtifactIndex(tmp_path / "demo.db").import_directory(source, synthetic=True)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="named pipes are unavailable on this platform")
def test_named_pipe_with_allowed_filename_is_rejected_without_blocking(tmp_path):
    source = artifact_tree(tmp_path)
    metrics = source / "fixture/baseline/metrics.json"
    metrics.unlink()
    os.mkfifo(metrics)

    with pytest.raises(ArtifactImportError, match="Unsafe artifact path"):
        ArtifactIndex(tmp_path / "demo.db").import_directory(source, synthetic=True)


def test_declared_dataset_identities_must_agree(tmp_path):
    source = artifact_tree(tmp_path)
    manifest_path = source / "fixture/baseline/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["input_dataset_sha256"] = "b" * 64
    _write_json(manifest_path, manifest)

    with pytest.raises(ArtifactImportError, match="dataset identities"):
        ArtifactIndex(tmp_path / "demo.db").import_directory(source, synthetic=True)


def test_missing_required_run_artifact_is_rejected(tmp_path):
    source = artifact_tree(tmp_path)
    (source / "fixture/baseline/diagnostics.json").unlink()

    with pytest.raises(ArtifactImportError, match="Missing required artifact"):
        ArtifactIndex(tmp_path / "demo.db").import_directory(source, synthetic=True)


def test_manifest_cost_settings_must_match_protocol(tmp_path):
    source = artifact_tree(tmp_path)
    manifest_path = source / "fixture/baseline/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["settings"]["SPREAD_BPS"] = 0.0
    _write_json(manifest_path, manifest)

    with pytest.raises(ArtifactImportError, match="costs disagree"):
        ArtifactIndex(tmp_path / "demo.db").import_directory(source, synthetic=True)


def test_synthetic_label_must_match_explicit_source_evidence(tmp_path):
    source = artifact_tree(tmp_path)

    with pytest.raises(ArtifactImportError, match="must retain that label"):
        ArtifactIndex(tmp_path / "demo.db").import_directory(source, synthetic=False)


def test_saved_provenance_must_be_backtest_local(tmp_path):
    source = artifact_tree(tmp_path)
    manifest_path = source / "fixture/baseline/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["backend"] = "paper"
    _write_json(manifest_path, manifest)

    with pytest.raises(ArtifactImportError, match="backtest/local"):
        ArtifactIndex(tmp_path / "demo.db").import_directory(source, synthetic=True)


def test_source_change_between_snapshot_and_commit_is_rejected(tmp_path, monkeypatch):
    source = artifact_tree(tmp_path)
    original_verify = artifacts._SourceSnapshot.verify_unchanged

    def mutate_then_verify(snapshot):
        (source / "fixture/baseline/metrics.json").write_text('{"changed": true}')
        original_verify(snapshot)

    monkeypatch.setattr(artifacts._SourceSnapshot, "verify_unchanged", mutate_then_verify)
    with pytest.raises(ArtifactImportError, match="changed during import"):
        ArtifactIndex(tmp_path / "demo.db").import_directory(source, synthetic=True)


def test_same_content_at_a_different_source_directory_is_rejected(tmp_path):
    source = artifact_tree(tmp_path)
    relocated = tmp_path / "relocated-synthetic-result"
    shutil.copytree(source, relocated)
    index = ArtifactIndex(tmp_path / "demo.db")
    index.import_directory(source, synthetic=True)

    with pytest.raises(ArtifactImportError, match="different source directory"):
        index.import_directory(relocated, synthetic=True)


def test_projection_column_migrates_old_index_before_import(tmp_path):
    db = tmp_path / "old-demo.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            """CREATE TABLE demo_artifact_imports (
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, source_directory TEXT NOT NULL UNIQUE,
                scenario_name TEXT NOT NULL, protocol_sha256 TEXT NOT NULL,
                source_manifest_sha256 TEXT NOT NULL, metadata_json TEXT NOT NULL,
                imported_at TEXT NOT NULL)"""
        )
    ArtifactIndex(db).import_directory(artifact_tree(tmp_path), synthetic=True)

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT projection_sha256, metadata_json, imported_at FROM demo_artifact_imports"
        ).fetchone()
    assert len(row[0]) == 64
    assert "protocol.json" in row[1]
    assert row[2]


def test_owner_scope_does_not_reuse_another_owners_index(tmp_path):
    source = artifact_tree(tmp_path)
    index = ArtifactIndex(tmp_path / "demo.db")
    index.import_directory(source, owner_id="owner-a", synthetic=True)

    with pytest.raises(ArtifactImportError, match="different owner"):
        index.import_directory(source, owner_id="owner-b", synthetic=True)

"""Offline coverage for the bounded, read-only A3 Flask API."""

import json
import sqlite3
import uuid
from pathlib import Path

from dashboard.app import create_app
from demo.artifacts import ArtifactIndex


ROOT = Path(__file__).resolve().parents[1]


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))


def artifact_tree(tmp_path):
    """A portable one-result A2 source tree; no production artifact is touched."""
    fixture = json.loads((ROOT / "docs/engine-demo/fixtures/synthetic-source.json").read_text())
    source = tmp_path / "synthetic-result"
    protocol = dict(fixture["protocol"])
    digest = "a" * 64
    protocol.update(synthetic=True, dataset_file_sha256=digest,
                    unprojected_protocol_field={"internal": True})
    protocol["dataset_metadata"] = dict(protocol["dataset_metadata"], dataset_file_sha256=digest)
    row = dict(fixture["comparison"][0])
    manifest = dict(fixture["manifest"])
    manifest.update(window=row["window"], gate=row["variant"], input_dataset_sha256=digest,
                    dataset_metadata={"dataset_file_sha256": digest},
                    settings={"SPREAD_BPS": 2.0, "SLIPPAGE_BPS": 1.0, "FEE_PER_SHARE": 0.0})
    _write_json(source / "protocol.json", protocol)
    _write_json(source / "comparison.json", [row])
    _write_json(source / "fixture/baseline/manifest.json", manifest)
    _write_json(source / "fixture/baseline/metrics.json", row["metrics"])
    _write_json(source / "fixture/baseline/diagnostics.json", row["diagnostics"])
    return source


def _client_with_saved_result(tmp_path, *, owner="owner-a"):
    source = artifact_tree(tmp_path)
    demo_db = tmp_path / "demo-artifacts.db"
    report = ArtifactIndex(demo_db).import_directory(source, owner_id=owner, synthetic=True)
    client = create_app(db_path=str(tmp_path / "operational.db"), demo_db_path=str(demo_db),
                        demo_owner_id=owner).test_client()
    return client, demo_db, source, report.result_ids[0]


def _assert_envelope(response):
    assert response.status_code == 200
    body = response.get_json()
    assert set(body) == {"schema_version", "data", "warnings"}
    assert body["schema_version"] == 1
    assert isinstance(body["warnings"], list)
    return body


def test_catalog_and_research_responses_are_versioned_and_descriptive(tmp_path):
    client, _, _, result_id = _client_with_saved_result(tmp_path)

    strategies = _assert_envelope(client.get("/api/demo/v1/strategies"))
    datasets = _assert_envelope(client.get("/api/demo/v1/datasets"))
    costs = _assert_envelope(client.get("/api/demo/v1/cost-profiles"))
    research = _assert_envelope(client.get("/api/demo/v1/research?limit=1"))
    detail = _assert_envelope(client.get("/api/demo/v1/results/%s" % result_id))

    assert strategies["data"][0]["record_type"] == "strategy"
    assert strategies["data"][0]["editable_fields"] == []
    assert datasets["data"]["datasets"][0]["approved_windows"] == []
    assert datasets["data"]["datasets"][0]["requested_bounds"]["availability"] == "unavailable"
    assert costs["data"]["cost_profiles"][0]["catalog_kind"] == "saved_source_description"
    assert research["data"]["results"][0]["id"] == result_id
    assert detail["data"]["result"]["id"] == result_id
    assert detail["data"]["status"]["origin"] == "saved_artifact"
    assert detail["data"]["status"]["created_at"]["availability"] == "unavailable"
    # A2's internal source metadata is deliberately not part of any A3 response.
    encoded = json.dumps(detail)
    assert "unprojected_protocol_field" not in encoded
    assert "source_directory" not in encoded


def test_owner_scope_and_path_like_ids_are_not_disclosed(tmp_path):
    client, demo_db, _, result_id = _client_with_saved_result(tmp_path)
    source_b = artifact_tree(tmp_path / "other-owner")
    protocol = json.loads((source_b / "protocol.json").read_text())
    protocol["label"] = "separate-owner-source"
    (source_b / "protocol.json").write_text(json.dumps(protocol))
    other_result = ArtifactIndex(demo_db).import_directory(source_b, owner_id="owner-b", synthetic=True).result_ids[0]
    artifact_id = _assert_envelope(client.get("/api/demo/v1/results/%s" % result_id))["data"]["artifacts"][0]["id"]

    assert client.get("/api/demo/v1/results/%s" % other_result).status_code == 404
    assert client.get("/api/demo/v1/results/not-a-uuid").status_code == 404
    assert client.get("/api/demo/v1/results/..%2Fetc%2Fpasswd").status_code == 404
    assert client.get("/api/demo/v1/results/%s/artifacts/%s" % (uuid.uuid4(), artifact_id)).status_code == 404
    assert client.get("/api/demo/v1/results/%s/artifacts/..%%2Fmetrics.json" % result_id).status_code == 404


def test_artifact_is_result_scoped_reverified_and_bounded(tmp_path):
    client, _, source, result_id = _client_with_saved_result(tmp_path)
    detail = _assert_envelope(client.get("/api/demo/v1/results/%s" % result_id))
    artifact_id = next(item["id"] for item in detail["data"]["artifacts"] if item["kind"] == "metrics")
    path = source / "fixture/baseline/metrics.json"

    response = client.get("/api/demo/v1/results/%s/artifacts/%s" % (result_id, artifact_id))
    assert response.status_code == 200
    assert response.data == path.read_bytes()
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    path.unlink()
    assert client.get("/api/demo/v1/results/%s/artifacts/%s" % (result_id, artifact_id)).status_code == 404


def test_artifact_and_json_response_limits_are_enforced(tmp_path):
    source = artifact_tree(tmp_path)
    (source / "comparison.md").write_bytes(b"x" * (1024 * 1024 + 1))
    demo_db = tmp_path / "demo-artifacts.db"
    result_id = ArtifactIndex(demo_db).import_directory(source, synthetic=True).result_ids[0]
    client = create_app(db_path=str(tmp_path / "operational.db"), demo_db_path=str(demo_db)).test_client()
    detail = _assert_envelope(client.get("/api/demo/v1/results/%s" % result_id))
    large_id = next(item["id"] for item in detail["data"]["artifacts"] if item["kind"] == "report")
    assert client.get("/api/demo/v1/results/%s/artifacts/%s" % (result_id, large_id)).status_code == 413

    with sqlite3.connect(demo_db) as conn:
        original = conn.execute(
            "SELECT import_id, owner_id, result_json FROM demo_artifact_results WHERE id=?", (result_id,)
        ).fetchone()
        result = json.loads(original[2])
        # This fits the old UTF-8 approximation (<512KiB across two records) but
        # Flask escapes it to a response well over 512KiB by default.
        result["display_only_oversize"] = "é" * 60_000
        for index in range(2):
            copied_id, copied_run_id = str(uuid.uuid4()), str(uuid.uuid4())
            copied = dict(result, id=copied_id, run_id=copied_run_id)
            conn.execute(
                """INSERT INTO demo_artifact_results
                   (id, import_id, owner_id, run_id, window_name, variant, result_json, run_json)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (copied_id, original[0], original[1], copied_run_id, "fixture-copy-%d" % index,
                 "baseline", json.dumps(copied, ensure_ascii=False), '{"record_type":"normalized_run"}'),
            )
    assert client.get("/api/demo/v1/research").status_code == 413


def test_missing_run_fields_produce_safe_dataset_unavailability(tmp_path):
    client, demo_db, _, result_id = _client_with_saved_result(tmp_path)
    with sqlite3.connect(demo_db) as conn:
        run = json.loads(conn.execute("SELECT run_json FROM demo_artifact_results WHERE id=?", (result_id,)).fetchone()[0])
        run.pop("feed")
        run.pop("dataset_sha256")
        conn.execute("UPDATE demo_artifact_results SET run_json=? WHERE id=?", (json.dumps(run), result_id))

    body = _assert_envelope(client.get("/api/demo/v1/datasets"))
    dataset = body["data"]["datasets"][0]
    assert dataset["feed"]["availability"] == "unavailable"
    assert dataset["content_sha256"]["availability"] == "unavailable"
    assert client.get("/api/demo/v1/research?limit=51").status_code == 400


def test_missing_dataset_provenance_is_not_defaulted_to_non_synthetic(tmp_path):
    client, demo_db, _, result_id = _client_with_saved_result(tmp_path)
    with sqlite3.connect(demo_db) as conn:
        run = json.loads(conn.execute("SELECT run_json FROM demo_artifact_results WHERE id=?", (result_id,)).fetchone()[0])
        run.pop("provenance")
        conn.execute("UPDATE demo_artifact_results SET run_json=? WHERE id=?", (json.dumps(run), result_id))

    body = _assert_envelope(client.get("/api/demo/v1/datasets"))
    assert body["data"]["datasets"] == []
    assert any("missing provenance evidence" in warning for warning in body["warnings"])

import importlib.util
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dashboard.app import create_app
from demo.jobs import FAILURE_SUMMARIES, IdempotencyConflict, JobStore, LeaseLost, requester_id_for
from demo.read_service import DemoNotFound
from demo.replay_catalog import ReplayRequestRejected

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("engine_demo_contract", ROOT / "docs/engine-demo/validate.py")
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)

FIXTURE_ID = "6f1d0a52-3c1b-4f7e-9a51-0c6a1f4e2b10"
LEASE = 30


class FakeClock:
    def __init__(self):
        self.now = datetime(2026, 9, 24, 14, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


def run_request(**overrides):
    return {"strategy_id": "stock-signal", "dataset_id": FIXTURE_ID, "window_id": "fixture-day-2",
            "cost_profile_id": "base-v2", "idempotency_key": "click-0001", **overrides}


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def store(tmp_path, clock):
    return JobStore(tmp_path / "jobs.db", clock=clock)


def status_of(store, job_id, owner="local"):
    detail = store.job_detail(owner, job_id)
    status = detail["data"]["status"]
    contract.validate(contract.envelope(status))
    return status


def test_submit_queues_a_contract_valid_job(store):
    job_id, created = store.submit("local", run_request())
    assert created
    detail = store.job_detail("local", job_id)
    contract.validate(contract.envelope(detail["data"]["run"]))
    status = status_of(store, job_id)
    assert detail["data"]["run"]["id"] == status["run_id"] == job_id
    assert (status["origin"], status["state"], status["attempt"]["value"]) == ("job", "queued", 0)
    assert status["started_at"]["availability"] == "unavailable"


def test_same_key_and_request_returns_same_job_and_changed_request_conflicts(store):
    job_id, _ = store.submit("local", run_request())
    assert store.submit("local", run_request()) == (job_id, False)
    with pytest.raises(IdempotencyConflict):
        store.submit("local", run_request(cost_profile_id="adverse-v2"))
    other_id, created = store.submit("someone-else", run_request())
    assert created and other_id != job_id


def test_repeat_returns_the_run_without_rereading_a_changed_dataset(store, monkeypatch):
    job_id, _ = store.submit("local", run_request())

    def dataset_changed(_request):
        raise ReplayRequestRejected("dataset_changed", "Approved dataset bytes changed")

    monkeypatch.setattr("demo.jobs.build_replay_request", dataset_changed)
    assert store.submit("local", run_request()) == (job_id, False)
    with pytest.raises(IdempotencyConflict):
        store.submit("local", run_request(cost_profile_id="adverse-v2"))
    with pytest.raises(ReplayRequestRejected):
        store.submit("local", run_request(idempotency_key="click-0002"))


def test_rejected_request_creates_no_job(store):
    with pytest.raises(ReplayRequestRejected):
        store.submit("local", run_request(dataset_path="/etc/passwd"))
    assert store.list_jobs("local")["data"]["runs"] == []


def test_concurrent_duplicate_submits_create_one_job(tmp_path, clock):
    JobStore(tmp_path / "jobs.db", clock=clock)
    barrier, results, errors = threading.Barrier(6), [], []

    def click():
        try:
            barrier.wait()
            results.append(JobStore(tmp_path / "jobs.db", clock=clock).submit("local", run_request()))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=click) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert len({job_id for job_id, _ in results}) == 1
    assert sorted(created for _, created in results) == [False] * 5 + [True]


def test_concurrent_claims_lease_a_job_once(tmp_path, clock):
    JobStore(tmp_path / "jobs.db", clock=clock).submit("local", run_request())
    barrier, claims = threading.Barrier(6), []

    def claim():
        barrier.wait()
        claims.append(JobStore(tmp_path / "jobs.db", clock=clock).claim_next(lease_seconds=LEASE))

    threads = [threading.Thread(target=claim) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    won = [item for item in claims if item is not None]
    assert len(won) == 1 and won[0].attempt == 1


def test_timestamps_are_read_after_waiting_for_the_lock(tmp_path, store, clock):
    store.submit("local", run_request())
    blocker = sqlite3.connect(tmp_path / "jobs.db", isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    claims = []
    worker = threading.Thread(target=lambda: claims.append(store.claim_next(lease_seconds=LEASE)))
    worker.start()
    time.sleep(0.3)
    clock.advance(5)
    blocker.execute("COMMIT")
    blocker.close()
    worker.join()
    status = status_of(store, claims[0].id)
    assert status["started_at"]["value"] == clock.now.isoformat()
    assert status["created_at"]["value"] < status["started_at"]["value"]


def test_claim_returns_the_stored_request_for_the_worker(store):
    job_id, _ = store.submit("local", run_request())
    claimed = store.claim_next(lease_seconds=LEASE)
    assert claimed.id == job_id
    assert claimed.request == run_request()
    assert claimed.normalized_run["id"] == job_id
    assert claimed.strategy_configuration["template_version"]
    status = status_of(store, job_id)
    assert (status["state"], status["phase"]["value"]) == ("running", "validating")
    assert store.claim_next(lease_seconds=LEASE) is None


def test_other_owner_and_malformed_ids_are_not_found(store):
    job_id, _ = store.submit("local", run_request())
    for owner, run_id in (("someone-else", job_id), ("local", "../jobs.db"), ("local", job_id.upper())):
        with pytest.raises(DemoNotFound):
            store.job_detail(owner, run_id)
        with pytest.raises(DemoNotFound):
            store.request_cancel(owner, run_id)
    assert store.list_jobs("someone-else")["data"]["runs"] == []


def test_cancelling_a_queued_job_ends_it_before_any_claim(store):
    job_id, _ = store.submit("local", run_request())
    first = store.request_cancel("local", job_id)["data"]["status"]
    assert first["state"] == "cancelled"
    assert first["cancellation"]["requester_id"] == requester_id_for("local")
    assert store.request_cancel("local", job_id)["data"]["status"] == first
    assert store.claim_next(lease_seconds=LEASE) is None
    status_of(store, job_id)


def test_cancelling_a_running_job_waits_for_the_worker(store):
    job_id, _ = store.submit("local", run_request())
    claimed = store.claim_next(lease_seconds=LEASE)
    assert store.request_cancel("local", job_id)["data"]["status"]["state"] == "cancel_requested"
    assert status_of(store, job_id)["ended_at"]["availability"] == "unavailable"
    assert store.heartbeat(job_id, claimed.lease_token, lease_seconds=LEASE, phase="replaying") == "cancel_requested"
    store.confirm_cancelled(job_id, claimed.lease_token)
    assert status_of(store, job_id)["state"] == "cancelled"
    assert store.request_cancel("local", job_id)["data"]["status"]["state"] == "cancelled"


def test_completion_published_before_cancel_wins(store):
    job_id, _ = store.submit("local", run_request())
    claimed = store.claim_next(lease_seconds=LEASE)
    store.request_cancel("local", job_id)
    result_id = str(uuid.uuid4())
    store.complete(job_id, claimed.lease_token, engine_run_id="engine-run-1", result_id=result_id)
    status = status_of(store, job_id)
    assert (status["state"], status["result_id"]["value"], status["engine_run_id"]["value"]) == (
        "completed", result_id, "engine-run-1")


def test_terminal_jobs_stay_terminal(store):
    job_id, _ = store.submit("local", run_request())
    claimed = store.claim_next(lease_seconds=LEASE)
    store.fail(job_id, claimed.lease_token, code="execution_failed")
    failed = status_of(store, job_id)
    assert failed["failure"]["code"] == "execution_failed"
    assert failed["failure"]["summary"] == FAILURE_SUMMARIES["execution_failed"]
    assert store.request_cancel("local", job_id)["data"]["status"] == failed
    with pytest.raises(LeaseLost):
        store.complete(job_id, claimed.lease_token, engine_run_id="late", result_id=str(uuid.uuid4()))
    with pytest.raises(LeaseLost):
        store.confirm_cancelled(job_id, claimed.lease_token)


def test_failure_summaries_are_fixed_per_code():
    contract_codes = contract.SCHEMA["$defs"]["failure"]["properties"]["code"]["enum"]
    assert sorted(FAILURE_SUMMARIES) == sorted(contract_codes)
    assert all(0 < len(summary) <= 500 for summary in FAILURE_SUMMARIES.values())


def test_confirming_cancel_without_a_request_is_refused(store):
    job_id, _ = store.submit("local", run_request())
    claimed = store.claim_next(lease_seconds=LEASE)
    with pytest.raises(LeaseLost):
        store.confirm_cancelled(job_id, claimed.lease_token)
    assert status_of(store, job_id)["state"] == "running"


def test_unknown_failure_code_and_phase_are_rejected(store):
    job_id, _ = store.submit("local", run_request())
    claimed = store.claim_next(lease_seconds=LEASE)
    with pytest.raises(ValueError):
        store.fail(job_id, claimed.lease_token, code="Traceback")
    with pytest.raises(ValueError):
        store.heartbeat(job_id, claimed.lease_token, lease_seconds=LEASE, phase="uploading")
    assert status_of(store, job_id)["state"] == "running"


def test_restart_requeues_a_lost_attempt_once_then_fails_worker_lost(store, clock):
    job_id, _ = store.submit("local", run_request())
    first = store.claim_next(lease_seconds=LEASE)
    clock.advance(LEASE - 1)
    assert store.recover_expired_leases() == {}
    clock.advance(2)
    assert store.recover_expired_leases() == {job_id: "queued"}
    requeued = status_of(store, job_id)
    assert (requeued["state"], requeued["attempt"]["value"]) == ("queued", 1)
    assert requeued["started_at"]["availability"] == "unavailable"
    with pytest.raises(LeaseLost):
        store.heartbeat(job_id, first.lease_token, lease_seconds=LEASE)

    second = store.claim_next(lease_seconds=LEASE)
    assert second.attempt == 2 and second.lease_token != first.lease_token
    clock.advance(LEASE + 1)
    assert store.recover_expired_leases() == {job_id: "failed"}
    failed = status_of(store, job_id)
    assert (failed["failure"]["code"], failed["failure"]["retryable"]) == ("worker_lost", False)


def test_heartbeat_keeps_the_lease_alive(store, clock):
    job_id, _ = store.submit("local", run_request())
    claimed = store.claim_next(lease_seconds=LEASE)
    clock.advance(LEASE - 1)
    store.heartbeat(job_id, claimed.lease_token, lease_seconds=LEASE, phase="exporting")
    heartbeat_at = clock.now.isoformat()
    clock.advance(LEASE - 1)
    assert store.recover_expired_leases() == {}
    status = status_of(store, job_id)
    assert (status["phase"]["value"], status["heartbeat_at"]["value"]) == ("exporting", heartbeat_at)


def test_expired_lease_is_refused_before_recovery_runs(store, clock):
    job_id, _ = store.submit("local", run_request())
    claimed = store.claim_next(lease_seconds=LEASE)
    clock.advance(LEASE + 1)
    with pytest.raises(LeaseLost):
        store.heartbeat(job_id, claimed.lease_token, lease_seconds=LEASE)
    with pytest.raises(LeaseLost):
        store.fail(job_id, claimed.lease_token, code="execution_failed")
    assert store.recover_expired_leases() == {job_id: "queued"}
    with pytest.raises(LeaseLost):
        store.complete(job_id, claimed.lease_token, engine_run_id="late", result_id=str(uuid.uuid4()))


def test_result_published_after_expiry_completes_before_recovery(store, clock):
    job_id, _ = store.submit("local", run_request())
    claimed = store.claim_next(lease_seconds=LEASE)
    store.request_cancel("local", job_id)
    clock.advance(LEASE + 1)
    result_id = str(uuid.uuid4())
    store.complete(job_id, claimed.lease_token, engine_run_id="engine-run-1", result_id=result_id)
    assert store.recover_expired_leases() == {}
    assert store.claim_next(lease_seconds=LEASE) is None
    status = status_of(store, job_id)
    assert (status["state"], status["result_id"]["value"]) == ("completed", result_id)


@pytest.mark.parametrize("lease_seconds", [0, -5, float("inf"), float("nan"), True, "30"])
def test_lease_duration_must_be_positive_and_finite(store, lease_seconds):
    job_id, _ = store.submit("local", run_request())
    with pytest.raises(ValueError):
        store.claim_next(lease_seconds=lease_seconds)
    claimed = store.claim_next(lease_seconds=LEASE)
    with pytest.raises(ValueError):
        store.heartbeat(job_id, claimed.lease_token, lease_seconds=lease_seconds)


def test_restart_settles_a_lost_cancel_request_as_cancelled(store, clock):
    job_id, _ = store.submit("local", run_request())
    store.claim_next(lease_seconds=LEASE)
    store.request_cancel("local", job_id)
    clock.advance(LEASE + 1)
    assert store.recover_expired_leases() == {job_id: "cancelled"}
    assert status_of(store, job_id)["state"] == "cancelled"


def test_list_is_newest_first_with_a_scoped_cursor(store, clock):
    ids = []
    for index in range(3):
        ids.append(store.submit("local", run_request(idempotency_key="click-%04d" % index))[0])
        clock.advance(1)
    first = store.list_jobs("local", limit="2")["data"]
    assert [item["run_id"] for item in first["runs"]] == [ids[2], ids[1]]
    second = store.list_jobs("local", limit="2", cursor=first["next_cursor"])["data"]
    assert ([item["run_id"] for item in second["runs"]], second["next_cursor"]) == ([ids[0]], None)
    with pytest.raises(ValueError):
        store.list_jobs("someone-else", cursor=ids[0])
    with pytest.raises(ValueError):
        store.list_jobs("local", limit="0")


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path / "journal.db"), demo_db_path=str(tmp_path / "demo-artifacts.db"),
                     demo_job_db_path=str(tmp_path / "demo-jobs.db"))
    return app.test_client()


def test_api_submit_is_idempotent_and_reports_conflicts(client):
    first = client.post("/api/demo/v1/runs", json=run_request())
    assert first.status_code == 202
    job_id = first.get_json()["data"]["status"]["run_id"]
    assert first.headers["Location"] == "/api/demo/v1/runs/" + job_id
    repeat = client.post("/api/demo/v1/runs", json=run_request())
    assert (repeat.status_code, repeat.get_json()["data"]["status"]["run_id"]) == (202, job_id)
    conflict = client.post("/api/demo/v1/runs", json=run_request(cost_profile_id="adverse-v2"))
    assert (conflict.status_code, conflict.get_json()["error"]["code"]) == (409, "idempotency_conflict")


def test_api_rejects_unapproved_or_non_json_requests(client):
    forbidden = client.post("/api/demo/v1/runs", json=run_request(spread_bps=0))
    assert (forbidden.status_code, forbidden.get_json()["error"]["code"]) == (400, "unexpected_field")
    form = client.post("/api/demo/v1/runs", data=run_request())
    assert form.status_code == 415
    oversized = client.post("/api/demo/v1/runs", json=run_request(padding="x" * 5000))
    assert oversized.status_code == 413
    assert client.get("/api/demo/v1/runs").get_json()["data"]["runs"] == []


def test_api_list_detail_cancel_and_scope(client):
    job_id = client.post("/api/demo/v1/runs", json=run_request()).get_json()["data"]["status"]["run_id"]
    listed = client.get("/api/demo/v1/runs").get_json()
    assert [item["run_id"] for item in listed["data"]["runs"]] == [job_id]
    assert client.get("/api/demo/v1/runs/" + job_id).get_json()["data"]["status"]["state"] == "queued"
    cancelled = client.post("/api/demo/v1/runs/%s/cancel" % job_id, json={})
    assert (cancelled.status_code, cancelled.get_json()["data"]["status"]["state"]) == (200, "cancelled")


def test_api_run_errors_are_json_with_a_code(client):
    job_id = client.post("/api/demo/v1/runs", json=run_request()).get_json()["data"]["status"]["run_id"]
    for response, expected in (
        (client.get("/api/demo/v1/runs/" + str(uuid.uuid4())), (404, "not_found")),
        (client.get("/api/demo/v1/runs/not-a-uuid"), (404, "not_found")),
        (client.post("/api/demo/v1/runs/%s/cancel" % uuid.uuid4(), json={}), (404, "not_found")),
        (client.get("/api/demo/v1/runs?cursor=" + str(uuid.uuid4())), (400, "invalid_request")),
        (client.get("/api/demo/v1/runs?limit=0"), (400, "invalid_request")),
        (client.post("/api/demo/v1/runs/%s/cancel" % job_id), (415, "unsupported_media_type")),
    ):
        assert (response.status_code, response.get_json()["error"]["code"]) == expected
    assert client.get("/api/demo/v1/runs/" + job_id).get_json()["data"]["status"]["state"] == "queued"


def test_api_status_read_failure_after_enqueue_is_json(client, monkeypatch):
    def locked(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(JobStore, "job_detail", locked)
    response = client.post("/api/demo/v1/runs", json=run_request())
    assert (response.status_code, response.get_json()["error"]["code"]) == (503, "job_store_busy")
    assert "Location" not in response.headers
    monkeypatch.undo()
    assert len(client.get("/api/demo/v1/runs").get_json()["data"]["runs"]) == 1


def test_api_jobs_leave_the_engine_journal_untouched(client, tmp_path):
    client.post("/api/demo/v1/runs", json=run_request())
    with sqlite3.connect(tmp_path / "journal.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    with sqlite3.connect(tmp_path / "demo-jobs.db") as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "runs" not in tables and "demo_jobs" in tables

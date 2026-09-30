"""Offline C3 adapter checks; PostgreSQL RLS/locking still needs staging verification."""
import uuid

import pytest

from demo.hosted_identity import Scope
from demo.hosted_jobs import HostedJobStore, IdempotencyConflict, LeaseLost, hash_document


def uid():
    return str(uuid.uuid4())


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class ScriptedConnection:
    def __init__(self, steps):
        self.steps = list(steps)
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if not self.steps:
            raise AssertionError("Unexpected SQL: " + sql)
        fragment, rows = self.steps.pop(0)
        assert fragment in sql, sql
        return Result(rows)

    def done(self):
        assert self.steps == []


def test_submit_is_atomic_and_skips_duplicate_normalization():
    scope = Scope(uid(), uid(), "operator")
    run = uid()
    document = {"id": run}
    digest = hash_document(document)
    store = HostedJobStore()
    conn = ScriptedConnection([
        ("SELECT id,request_hash", []), ("SAVEPOINT hosted_submit", []),
        ("INSERT INTO hosted_resources", [(run,)]),
        ("INSERT INTO hosted_runs", [(run,)]),
        ("INSERT INTO hosted_outbox", []), ("RELEASE SAVEPOINT hosted_submit", []),
    ])
    assert store.submit(conn, scope, key="k", request_hash=digest,
                        configuration_hash=digest, request_document=document,
                        configuration_document=document, run_id=run) == (run, True)
    conn.done()
    assert conn.calls[3][1][0:3] == (scope.tenant_id, run, scope.user_id)

    repeated = ScriptedConnection([("SELECT id,request_hash", [(run, digest, digest)])])
    assert store.submit(repeated, scope, key="k", request_hash=digest,
                        configuration_hash=digest, request_document=document,
                        configuration_document=document) == (run, False)
    repeated.done()
    conflicting = ScriptedConnection([("SELECT id,request_hash", [(run, digest, "b" * 64)])])
    with pytest.raises(IdempotencyConflict):
        store.submit(conflicting, scope, key="k", request_hash=digest,
                     configuration_hash=digest, request_document=document,
                     configuration_document=document)


def test_concurrent_loser_rolls_back_orphan_registry_row():
    scope = Scope(uid(), uid(), "owner")
    winner, loser = uid(), uid()
    digest = hash_document({})
    conn = ScriptedConnection([
        ("SELECT id,request_hash", []), ("SAVEPOINT hosted_submit", []),
        ("INSERT INTO hosted_resources", [(loser,)]),
        ("INSERT INTO hosted_runs", []),
        ("ROLLBACK TO SAVEPOINT hosted_submit", []),
        ("RELEASE SAVEPOINT hosted_submit", []),
        ("SELECT id,request_hash", [(winner, digest, digest)]),
    ])
    assert HostedJobStore().submit(conn, scope, key="same", request_hash=digest,
                                   configuration_hash=digest, request_document={},
                                   configuration_document={}, run_id=loser) == (winner, False)
    conn.done()
    assert not any("INSERT INTO hosted_outbox" in sql for sql, _ in conn.calls)


def test_claim_uses_skip_locked_and_lease_fencing():
    tenant, run, token = uid(), uid(), uid()
    conn = ScriptedConnection([
        ("FOR UPDATE SKIP LOCKED LIMIT 1", [(tenant, run, 0, {"dataset_id": "fixture"}, {"gate": "baseline"})]),
        ("UPDATE hosted_runs SET state='running'", []),
        ("INSERT INTO hosted_run_attempts", []),
    ])
    claimed = HostedJobStore.claim_next(conn, lease_seconds=30)
    assert claimed["run_id"] == run and claimed["attempt"] == 1
    assert claimed["request"] == {"dataset_id": "fixture"}
    assert claimed["configuration"] == {"gate": "baseline"}
    conn.done()
    assert conn.calls[2][1][0:3] == (tenant, run, 1)

    heartbeat = ScriptedConnection([
        ("FOR UPDATE OF r,a", [("running", 1, "later", None, "validating")]),
        ("SELECT %s < clock_timestamp()", [(False,)]),
        ("UPDATE hosted_run_attempts SET heartbeat_at", []),
    ])
    assert HostedJobStore.heartbeat(heartbeat, tenant_id=tenant, run_id=run,
                                    lease_token=token, lease_seconds=30) == "running"
    heartbeat.done()
    assert heartbeat.calls[2][1][-3:] == (tenant, run, 1)

    backwards = ScriptedConnection([
        ("FOR UPDATE OF r,a", [("running", 1, "later", None, "verifying")]),
        ("SELECT %s < clock_timestamp()", [(False,)]),
    ])
    with pytest.raises(ValueError, match="backward"):
        HostedJobStore.heartbeat(backwards, tenant_id=tenant, run_id=run,
                                 lease_token=token, lease_seconds=30, phase="replaying")
    backwards.done()

    stale = ScriptedConnection([("FOR UPDATE OF r,a", [])])
    with pytest.raises(LeaseLost):
        HostedJobStore.heartbeat(stale, tenant_id=tenant, run_id=run,
                                 lease_token=token, lease_seconds=30)


def test_duplicate_completion_matches_content_and_token():
    tenant, run, token, result = (uid() for _ in range(4))
    digest = "a" * 64
    conn = ScriptedConnection([
        ("SELECT x.id,x.content_hash,r.state", [(result, digest, "completed")]),
    ])
    assert HostedJobStore().complete(conn, tenant_id=tenant, run_id=run, lease_token=token,
                                     result_id=result, content_hash=digest,
                                     result_document={"id": result, "run_id": run,
                                                      "artifact_ids": []}) is False
    conn.done()
    changed = ScriptedConnection([
        ("SELECT x.id,x.content_hash,r.state", [(result, "b" * 64, "completed")]),
    ])
    with pytest.raises(ValueError, match="Conflicting publication"):
        HostedJobStore().complete(changed, tenant_id=tenant, run_id=run, lease_token=token,
                                  result_id=result, content_hash=digest,
                                  result_document={"id": result, "run_id": run,
                                                   "artifact_ids": []})


def test_hash_is_canonical_and_no_nonfinite_json():
    assert hash_document({"b": 2, "a": 1}) == hash_document({"a": 1, "b": 2})
    with pytest.raises(ValueError):
        hash_document({"bad": float("nan")})

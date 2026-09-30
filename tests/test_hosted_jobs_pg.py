"""Real PostgreSQL C3 gate. Run only against a disposable PostgreSQL cluster.

Set HOSTED_PG_TEST_DSN to an administrative connection. This test creates and
removes its own database and unique runtime roles; it never uses broker credentials.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg import sql
from psycopg.conninfo import make_conninfo

from demo.hosted_identity import BoundaryDenied, Scope
from demo.hosted_jobs import HostedJobStore, IdempotencyConflict, LeaseLost, hash_document


ROOT = Path(__file__).resolve().parents[1]
STORE = HostedJobStore()


def uid():
    return str(uuid.uuid4())


@pytest.fixture(scope="module")
def pg_cluster():
    admin_dsn = os.environ.get("HOSTED_PG_TEST_DSN")
    if not admin_dsn:
        pytest.skip("Set HOSTED_PG_TEST_DSN to run the PostgreSQL gate")
    suffix = uuid.uuid4().hex[:12]
    database = "hosted_test_" + suffix
    api_role, worker_role = "hosted_api_" + suffix, "hosted_worker_" + suffix
    # Dedicated disposable cluster only; this is a public synthetic fixture value.
    api_password = worker_password = "fixture-only"
    created_group = False
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        # Only objects created by this fixture are removed. A pre-existing
        # hosted_worker group is preserved.
        if not admin.execute("SELECT 1 FROM pg_roles WHERE rolname='hosted_worker'").fetchone():
            admin.execute("CREATE ROLE hosted_worker NOLOGIN")
            created_group = True
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
            sql.Identifier(api_role), sql.Literal(api_password)))
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
            sql.Identifier(worker_role), sql.Literal(worker_password)))
        admin.execute(sql.SQL("GRANT hosted_worker TO {}").format(sql.Identifier(worker_role)))
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    database_dsn = make_conninfo(admin_dsn, dbname=database)
    try:
        with psycopg.connect(database_dsn, autocommit=True) as admin:
            for migration in ("001_hosted_identity.sql", "002_hosted_jobs.sql"):
                admin.execute((ROOT / "demo" / "migrations" / migration).read_text())
            # Match the minimum deployment grants, not a superuser API session.
            admin.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(
                sql.Identifier(database), sql.Identifier(api_role), sql.Identifier(worker_role)))
            admin.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}, {}").format(
                sql.Identifier(api_role), sql.Identifier(worker_role)))
            admin.execute(sql.SQL("GRANT SELECT ON hosted_memberships TO {}").format(sql.Identifier(api_role)))
            admin.execute(sql.SQL("GRANT SELECT,INSERT ON hosted_resources TO {}").format(sql.Identifier(api_role)))
            admin.execute(sql.SQL("GRANT SELECT,INSERT,UPDATE ON hosted_runs TO {}").format(sql.Identifier(api_role)))
            admin.execute(sql.SQL("GRANT SELECT ON hosted_run_attempts,hosted_results,"
                                  "hosted_result_artifacts TO {}").format(sql.Identifier(api_role)))
            admin.execute(sql.SQL("GRANT INSERT ON hosted_outbox TO {}").format(sql.Identifier(api_role)))
            admin.execute(sql.SQL("GRANT USAGE ON SEQUENCE hosted_outbox_id_seq TO {}").format(
                sql.Identifier(api_role)))
            tenants, users = (uid(), uid()), (uid(), uid())
            for tenant, user in zip(tenants, users):
                admin.execute("INSERT INTO hosted_tenants (id) VALUES (%s)", (tenant,))
                admin.execute("INSERT INTO hosted_users (id,issuer,subject) VALUES (%s,%s,%s)",
                              (user, "https://fixture.test", user))
                admin.execute("INSERT INTO hosted_memberships (tenant_id,user_id,role) "
                              "VALUES (%s,%s,'operator')", (tenant, user))
        api_dsn = make_conninfo(database_dsn, user=api_role, password=api_password)
        worker_dsn = make_conninfo(database_dsn, user=worker_role, password=worker_password)
        yield {"admin": database_dsn, "api": api_dsn, "worker": worker_dsn,
               "scopes": tuple(Scope(user, tenant, "operator") for tenant, user in zip(tenants, users))}
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database)))
            admin.execute(sql.SQL("DROP ROLE IF EXISTS {}, {}").format(
                sql.Identifier(api_role), sql.Identifier(worker_role)))
            if created_group:
                admin.execute("DROP ROLE hosted_worker")


@contextmanager
def api_connection(pg_cluster, scope):
    with psycopg.connect(pg_cluster["api"]) as conn:
        conn.execute("SELECT set_config('app.user_id',%s,true)", (scope.user_id,))
        conn.execute("SELECT set_config('app.tenant_id',%s,true)", (scope.tenant_id,))
        yield conn


@contextmanager
def worker_connection(pg_cluster):
    with psycopg.connect(pg_cluster["worker"]) as conn:
        yield conn


@pytest.fixture(autouse=True)
def empty_job_tables(pg_cluster):
    with psycopg.connect(pg_cluster["admin"], autocommit=True) as conn:
        conn.execute("TRUNCATE hosted_resources CASCADE")


def submit(pg_cluster, scope, key):
    request = {"dataset_id": "synthetic", "key": key}
    configuration = {"gate": "baseline"}
    with api_connection(pg_cluster, scope) as conn:
        return STORE.submit(conn, scope, key=key, request_hash=hash_document(request),
                            configuration_hash=hash_document(configuration),
                            request_document=request, configuration_document=configuration)


def test_migrations_and_role_isolation(pg_cluster):
    first, second = pg_cluster["scopes"]
    run, created = submit(pg_cluster, first, "tenant-isolation")
    assert created
    with psycopg.connect(pg_cluster["api"]) as conn:
        # RLS must still deny reads when application code forgets the predicate.
        assert conn.execute("SELECT id FROM hosted_runs").fetchall() == []
        assert conn.execute("SELECT id FROM hosted_resources").fetchall() == []
    with api_connection(pg_cluster, second) as conn:
        assert conn.execute("SELECT id FROM hosted_runs").fetchall() == []
        assert conn.execute("SELECT id FROM hosted_resources").fetchall() == []
        assert conn.execute("UPDATE hosted_runs SET state='cancelled' WHERE id=%s RETURNING id",
                            (run,)).fetchone() is None
        with pytest.raises(BoundaryDenied):
            STORE.cancel(conn, second, run)
    with api_connection(pg_cluster, first) as conn:
        assert str(conn.execute("SELECT id FROM hosted_runs").fetchone()[0]) == run
    with worker_connection(pg_cluster) as conn:
        assert conn.execute("SELECT count(*) FROM hosted_outbox").fetchone()[0] == 1
    with pytest.raises(psycopg.errors.RaiseException, match="invalid API transition"):
        with api_connection(pg_cluster, first) as conn:
            conn.execute("UPDATE hosted_runs SET failure_code='worker_lost' WHERE id=%s", (run,))


def test_concurrent_submission_and_conflicting_key(pg_cluster):
    scope = pg_cluster["scopes"][0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit, pg_cluster, scope, "concurrent") for _ in range(2)]
        outcomes = [future.result() for future in futures]
    assert outcomes[0][0] == outcomes[1][0]
    assert sorted(created for _, created in outcomes) == [False, True]
    with api_connection(pg_cluster, scope) as conn:
        assert conn.execute("SELECT count(*) FROM hosted_runs WHERE id=%s", (outcomes[0][0],)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM hosted_resources WHERE kind='run'").fetchone()[0] == 1
        with pytest.raises(IdempotencyConflict):
            STORE.existing(conn, scope, "concurrent", "0" * 64, hash_document({"gate": "baseline"}))


def test_skip_locked_cancel_and_fenced_recovery(pg_cluster):
    scope = pg_cluster["scopes"][0]
    run, _ = submit(pg_cluster, scope, "lease")
    with worker_connection(pg_cluster) as first:
        claim = STORE.claim_next(first, lease_seconds=30)
        assert claim["run_id"] == run
        with worker_connection(pg_cluster) as second:
            assert STORE.claim_next(second, lease_seconds=30) is None
    with api_connection(pg_cluster, scope) as conn:
        assert STORE.cancel(conn, scope, run) == "running"
    with worker_connection(pg_cluster) as conn:
        assert STORE.heartbeat(conn, tenant_id=scope.tenant_id, run_id=run,
                               lease_token=claim["lease_token"], lease_seconds=30) == "cancel_requested"
        STORE.confirm_cancelled(conn, tenant_id=scope.tenant_id, run_id=run,
                                lease_token=claim["lease_token"])
    with worker_connection(pg_cluster) as conn:
        with pytest.raises(LeaseLost):
            STORE.heartbeat(conn, tenant_id=scope.tenant_id, run_id=run,
                            lease_token=claim["lease_token"], lease_seconds=30)

    retry_run, _ = submit(pg_cluster, scope, "retry")
    with worker_connection(pg_cluster) as conn:
        old = STORE.claim_next(conn, lease_seconds=30)
        assert old["run_id"] == retry_run
        conn.execute("UPDATE hosted_run_attempts SET lease_expires_at=clock_timestamp()-interval '1 second' "
                     "WHERE run_id=%s", (retry_run,))
    with worker_connection(pg_cluster) as conn:
        assert STORE.recover_expired(conn) == [(retry_run, "queued")]
    with worker_connection(pg_cluster) as conn:
        new = STORE.claim_next(conn, lease_seconds=30)
        assert new["run_id"] == retry_run and new["attempt"] == 2
        with pytest.raises(LeaseLost):
            STORE._current(conn, scope.tenant_id, retry_run, old["lease_token"])
        conn.execute("UPDATE hosted_run_attempts SET lease_expires_at=clock_timestamp()-interval '1 second' "
                     "WHERE run_id=%s AND number=2", (retry_run,))
    with worker_connection(pg_cluster) as conn:
        assert STORE.recover_expired(conn) == [(retry_run, "failed")]
        assert conn.execute("SELECT failure_code FROM hosted_dead_letters WHERE run_id=%s",
                            (retry_run,)).fetchone()[0] == "worker_lost"


def test_atomic_publication_and_immutable_metadata(pg_cluster):
    first, second = pg_cluster["scopes"]
    run, _ = submit(pg_cluster, first, "publication")
    with worker_connection(pg_cluster) as conn:
        claim = STORE.claim_next(conn, lease_seconds=30)
    result, artifact = uid(), uid()
    digest = "a" * 64
    document = {"id": result, "run_id": run, "artifact_ids": [artifact]}
    artifacts = ({"id": artifact, "kind": "metrics", "object_version": "fixture-version",
                  "sha256": digest, "mime_type": "application/json", "byte_size": 2},)
    kwargs = dict(tenant_id=first.tenant_id, run_id=run, lease_token=claim["lease_token"],
                  result_id=result, content_hash=digest, result_document=document, artifacts=artifacts)
    with pytest.raises(RuntimeError, match="synthetic rollback"):
        with worker_connection(pg_cluster) as conn:
            assert STORE.complete(conn, **kwargs) is True
            raise RuntimeError("synthetic rollback")
    with worker_connection(pg_cluster) as conn:
        assert conn.execute("SELECT count(*) FROM hosted_results WHERE run_id=%s", (run,)).fetchone()[0] == 0
        assert conn.execute("SELECT state FROM hosted_runs WHERE id=%s", (run,)).fetchone()[0] == "running"
    with worker_connection(pg_cluster) as conn:
        assert STORE.complete(conn, **kwargs) is True
    with worker_connection(pg_cluster) as conn:
        assert STORE.complete(conn, **kwargs) is False
        with pytest.raises(ValueError, match="Conflicting publication"):
            STORE.complete(conn, **{**kwargs, "content_hash": "b" * 64})
    with api_connection(pg_cluster, second) as conn:
        assert conn.execute("SELECT id FROM hosted_results").fetchall() == []
        assert conn.execute("SELECT id FROM hosted_result_artifacts").fetchall() == []
    with api_connection(pg_cluster, first) as conn:
        assert str(conn.execute("SELECT id FROM hosted_results").fetchone()[0]) == result
        assert str(conn.execute("SELECT id FROM hosted_result_artifacts").fetchone()[0]) == artifact
    with worker_connection(pg_cluster) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE hosted_results SET content_hash=%s WHERE id=%s", ("b" * 64, result))

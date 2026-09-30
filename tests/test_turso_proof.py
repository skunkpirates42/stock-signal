"""Offline proof checks; these never read Turso credentials or use the network."""
import pytest

from experiments.turso import store
from experiments.turso.probe import exercise, local_factory, require_empty, uid


def test_two_workspace_contract(tmp_path):
    report = exercise(local_factory(tmp_path / "a.db"), local_factory(tmp_path / "b.db"), uid(), uid())
    assert report["lease_recovery"] == "passed"


def test_resume_retains_prior_synthetic_evidence(tmp_path):
    a, b = local_factory(tmp_path / "a.db"), local_factory(tmp_path / "b.db")
    workspace_a, workspace_b = uid(), uid()
    exercise(a, b, workspace_a, workspace_b)
    with store.transaction(a) as conn:
        before = conn.execute("SELECT id,state,result FROM proof_jobs").fetchone()
    exercise(a, b, workspace_a, workspace_b, resume=True)
    with store.transaction(a) as conn:
        assert conn.execute("SELECT id,state,result FROM proof_jobs WHERE id=?", (before[0],)).fetchone() == before
        assert conn.execute("SELECT COUNT(*) FROM proof_jobs").fetchone() == (2,)


def test_rollback_failure_does_not_hide_original_error():
    class BrokenConnection:
        closed = False

        def execute(self, sql):
            raise ValueError("original")

        def rollback(self):
            raise RuntimeError("rollback also failed")

        def close(self):
            self.closed = True

    conn = BrokenConnection()
    with pytest.raises(ValueError, match="original"):
        with store.transaction(lambda: conn):
            pytest.fail("transaction must not start")
    assert conn.closed


def test_migration_failure_rolls_back_and_can_resume(tmp_path, monkeypatch):
    connect, workspace = local_factory(tmp_path / "a.db"), uid()
    store.migrate(connect, workspace, target=1)
    original = store.MIGRATIONS
    monkeypatch.setattr(store, "MIGRATIONS", original + (("CREATE TABLE proof_broken(id INTEGER)", "INVALID SQL"),))
    with pytest.raises(Exception):
        store.migrate(connect, workspace)
    with store.transaction(connect) as conn:
        assert conn.execute("SELECT MAX(version) FROM proof_migrations").fetchone() == (1,)
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name='proof_broken'").fetchall()
    monkeypatch.setattr(store, "MIGRATIONS", original)
    store.migrate(connect, workspace)
    store.migrate(connect, workspace)


def test_migration_drift_and_wrong_workspace_fail_closed(tmp_path):
    connect, workspace = local_factory(tmp_path / "a.db"), uid()
    store.migrate(connect, workspace)
    with pytest.raises(store.BoundaryDenied):
        store.migrate(connect, uid())
    with store.transaction(connect) as conn:
        conn.execute("UPDATE proof_migrations SET digest='changed' WHERE version=1")
    with pytest.raises(ValueError, match="drift"):
        store.migrate(connect, workspace)


def test_transaction_failure_preserves_job_state(tmp_path):
    connect, workspace = local_factory(tmp_path / "a.db"), uid()
    store.migrate(connect, workspace)
    jobs = store.Store(connect, workspace)
    run = jobs.submit("k", {})
    with pytest.raises(RuntimeError):
        with jobs.tx() as conn:
            conn.execute("UPDATE proof_jobs SET state='completed',result='{}' WHERE id=?", (run,))
            raise RuntimeError("simulated disconnect before commit")
    assert jobs.get(run) == ("queued", 0, None)


def test_refuse_existing_remote_tables(tmp_path):
    connect = local_factory(tmp_path / "a.db")
    require_empty(connect)
    with store.transaction(connect) as conn:
        conn.execute("CREATE TABLE valuable_data(id INTEGER)")
    with pytest.raises(ValueError, match="empty"):
        require_empty(connect)


@pytest.mark.parametrize("seconds", [0, -1, True, 3601, "30"])
def test_invalid_lease_duration(tmp_path, seconds):
    jobs = store.Store(local_factory(tmp_path / "unused.db"), uid())
    with pytest.raises(ValueError):
        jobs.claim(seconds)
    assert not (tmp_path / "unused.db").exists()

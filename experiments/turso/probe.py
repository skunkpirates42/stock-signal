"""Identical synthetic contract probe for offline SQLite and remote libSQL.

Run with ``python -m experiments.turso.probe`` (temporary local databases) or
``python -m experiments.turso.probe --remote`` (explicit disposable databases).
Remote mode never provisions/deletes databases or prints exceptions.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
import multiprocessing
import os
from pathlib import Path
import sqlite3
import tempfile
import traceback
import uuid
from urllib.parse import urlsplit

from .store import BoundaryDenied, IdempotencyConflict, LeaseLost, Router, Scope, Store, migrate, transaction


def uid():
    return str(uuid.uuid4())


def expect_error(kind, action):
    try:
        action()
    except kind:
        return
    raise AssertionError("Expected operation to be denied")


_worker_barrier = None


def _initialize_worker(barrier):
    global _worker_barrier
    _worker_barrier = barrier


def _worker_operation(connect, workspace, operation, args, kwargs):
    _worker_barrier.wait(timeout=30)
    return getattr(Store(connect, workspace), operation)(*args, **kwargs)


def parallel(connect, workspace, operation, *args, count=4, **kwargs):
    # libsql 0.1.11 holds the GIL during blocking execute/commit calls. Independent
    # spawned processes model deployed workers without Python-thread lock starvation.
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(count)
    with ProcessPoolExecutor(max_workers=count, mp_context=context,
                             initializer=_initialize_worker, initargs=(barrier,)) as pool:
        futures = [pool.submit(_worker_operation, connect, workspace, operation, args, kwargs)
                   for _ in range(count)]
        return [future.result() for future in futures]


def expire(connect, run):
    # Administrative fault injection avoids sleeps and depends on no client clock.
    with transaction(connect) as conn:
        conn.execute("UPDATE proof_jobs SET expires=0 WHERE id=? AND state='running'", (run,))


def exercise(connect_a, connect_b, workspace_a, workspace_b, *, resume=False):
    """All writes are synthetic and confined to proof_* tables in two databases."""
    for connect, workspace in ((connect_a, workspace_a), (connect_b, workspace_b)):
        if not resume:
            migrate(connect, workspace, target=1)
        migrate(connect, workspace)
        migrate(connect, workspace)

    a, b = Store(connect_a, workspace_a), Store(connect_b, workspace_b)
    sessions = {"a": Scope(uid(), workspace_a, "owner"), "b": Scope(uid(), workspace_b, "owner"),
                "viewer": Scope(uid(), workspace_a, "viewer")}

    def resolve(session):
        if session not in sessions:
            raise BoundaryDenied()
        return sessions[session]

    router = Router(resolve, {workspace_a: connect_a, workspace_b: connect_b})
    expect_error(BoundaryDenied, lambda: router.call("unknown", "submit", "k", {}))
    expect_error(BoundaryDenied, lambda: router.call("viewer", "submit", "k", {}))
    expect_error(BoundaryDenied, lambda: router.call("a", "claim"))
    request = {"dataset": "synthetic", "configuration": {"paper": True}}
    key = uid()  # Retain earlier proof rows when explicitly resuming.
    runs = parallel(connect_a, workspace_a, "submit", key, request)
    assert len(set(runs)) == 1
    run = runs[0]
    assert router.call("a", "submit", key, request) == run
    other = router.call("b", "submit", key, request)
    assert other != run
    expect_error(IdempotencyConflict, lambda: router.call("a", "submit", key, {}))
    expect_error(BoundaryDenied, lambda: router.call("b", "get", run))
    expect_error(BoundaryDenied, lambda: router.call("a", "get", other))
    # Detect a wrong server-side connection mapping before reading tenant data.
    wrong = Router(resolve, {workspace_a: connect_b})
    expect_error(BoundaryDenied, lambda: wrong.call("a", "get", other))
    expect_error(BoundaryDenied, lambda: migrate(connect_b, workspace_a))
    # A session that was accepted previously must be denied after revocation.
    del sessions["viewer"]
    expect_error(BoundaryDenied, lambda: router.call("viewer", "get", run))

    claims = [item for item in parallel(connect_a, workspace_a, "claim", run_id=run) if item is not None]
    assert len(claims) == 1
    assert claims[0][0] == run
    old_token = claims[0][1]
    expire(connect_a, run)
    a.recover()
    retry = a.claim(run_id=run)
    assert retry[2] == 2 and retry[1] != old_token
    expect_error(LeaseLost, lambda: a.complete(run, old_token, {}))
    expect_error(LeaseLost, lambda: b.complete(run, retry[1], {}))
    result = {"run_id": run, "paper": True}
    assert a.complete(run, retry[1], result)
    assert not a.complete(run, retry[1], result)
    expect_error(LeaseLost, lambda: a.complete(run, retry[1], {"changed": True}))
    a.recover()
    assert a.get(run)[0] == "completed"
    assert a.claim(run_id=run) is None

    # B remains independent; exhaust its two attempts without publication.
    for attempt in (1, 2):
        claim = b.claim(run_id=other)
        assert claim[0] == other and claim[2] == attempt
        expire(connect_b, other)
        b.recover()
    assert b.get(other)[0] == "failed" and b.claim(run_id=other) is None
    return {"workspaces": 2, "schema_version": 2, "concurrent_clients": 4,
            "client_model": "spawned-processes", "isolation": "passed", "idempotency": "passed", "claims": "passed",
            "lease_recovery": "passed", "publication": "passed", "migrations": "passed"}


@dataclass(frozen=True)
class local_factory:
    path: object

    def __call__(self):
        return sqlite3.connect(str(self.path), isolation_level=None, timeout=10)


@dataclass(frozen=True, repr=False)
class RemoteConnection:
    url: str = field(repr=False)
    token: str = field(repr=False)

    def __call__(self):
        import libsql
        return libsql.connect(database=self.url, auth_token=self.token, isolation_level=None)


def remote_factory(url, token):
    parsed = urlsplit(url)
    if (parsed.scheme not in {"libsql", "https"} or not parsed.hostname or
            not parsed.hostname.endswith(".turso.io") or parsed.username or parsed.password or
            parsed.query or parsed.fragment or parsed.path not in {"", "/"} or not token):
        raise ValueError("Expected a Turso libSQL database URL and token")
    return RemoteConnection(url, token)


def require_empty(connect):
    with transaction(connect) as conn:
        if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
            raise ValueError("Remote proof requires empty disposable databases")


def existing_workspace(connect):
    with transaction(connect) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()}
        if tables != {"proof_migrations", "proof_workspace", "proof_jobs"}:
            raise ValueError("Resume requires proof-only databases")
        row = conn.execute("SELECT id FROM proof_workspace WHERE singleton=1").fetchone()
        if row is None:
            raise ValueError("Missing proof workspace")
        return row[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", action="store_true")
    parser.add_argument("--env-file", help="Explicit credential file; never loaded by offline tests")
    parser.add_argument("--resume", action="store_true", help="Preserve existing proof-only databases and add a fresh scenario")
    args = parser.parse_args()
    try:
        if args.remote:
            names = ["TURSO_PROOF_" + side + suffix for side in ("A", "B") for suffix in ("_URL", "_TOKEN")]
            credentials = {name: os.environ.get(name) for name in names}
            if args.env_file:
                from dotenv import dotenv_values
                values = dotenv_values(args.env_file, interpolate=False)
                credentials = {name: values.get(name) for name in names}
            if not all(credentials.values()):
                print("Remote proof unavailable: configure TURSO_PROOF_A/B_URL and TURSO_PROOF_A/B_TOKEN.")
                return 2
            first, second = (credentials[name] for name in (names[0], names[2]))
            if urlsplit(first).hostname == urlsplit(second).hostname:
                raise ValueError("Two different databases required")
            a = remote_factory(first, credentials[names[1]])
            b = remote_factory(second, credentials[names[3]])
            if args.resume:
                workspace_a, workspace_b = existing_workspace(a), existing_workspace(b)
                if workspace_a == workspace_b:
                    raise ValueError("Distinct workspace bindings required")
            else:
                require_empty(a)
                require_empty(b)
                workspace_a, workspace_b = uid(), uid()
            report = exercise(a, b, workspace_a, workspace_b, resume=args.resume)
        else:
            with tempfile.TemporaryDirectory(prefix="turso-proof-") as root:
                report = exercise(local_factory(Path(root) / "a.db"), local_factory(Path(root) / "b.db"), uid(), uid())
        print({"backend": "remote-libsql" if args.remote else "local-sqlite", **report})
        return 0
    except Exception as error:
        # Driver exceptions can include URLs/headers. Never serialize them.
        frames = traceback.extract_tb(error.__traceback__)
        location = next((frame for frame in reversed(frames)
                         if Path(frame.filename).parent == Path(__file__).parent), None)
        print({"status": "failed", "error_type": type(error).__name__,
               "proof_function": location.name if location else "driver",
               "proof_line": location.lineno if location else None})
        print("No remote database was deleted. Exception text and locals are suppressed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

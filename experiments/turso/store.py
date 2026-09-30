"""Bounded database-per-workspace proof, deliberately outside the hosted API.

Factories return fresh DB-API connections to the authoritative database. No
embedded replicas, engine imports, automatic retries or production provisioning.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import uuid

class BoundaryDenied(Exception):
    def __init__(self, code="unauthenticated", status=401):
        self.code, self.status = code, status
        super().__init__(code)


class IdempotencyConflict(ValueError):
    pass


class LeaseLost(RuntimeError):
    pass


@dataclass(frozen=True)
class Scope:
    user_id: str
    tenant_id: str
    role: str

    def __post_init__(self):
        for value in (self.user_id, self.tenant_id):
            if str(uuid.UUID(value)) != value:
                raise ValueError("Canonical UUID required")
        if self.role not in {"owner", "operator", "viewer"}:
            raise ValueError("Invalid role")

    def require_write(self):
        if self.role == "viewer":
            raise BoundaryDenied("forbidden", 403)


def hash_document(document):
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


MIGRATIONS = (
    (
        "CREATE TABLE proof_workspace (singleton INTEGER PRIMARY KEY CHECK(singleton=1), id TEXT NOT NULL UNIQUE)",
        "CREATE TABLE proof_jobs (id TEXT PRIMARY KEY, key TEXT NOT NULL UNIQUE, digest TEXT NOT NULL, request TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('queued','running','completed','failed')), attempt INTEGER NOT NULL DEFAULT 0, token TEXT, expires INTEGER, result TEXT)",
    ),
    ("CREATE INDEX proof_jobs_pending ON proof_jobs(state, expires)",),
)


@contextmanager
def transaction(connect):
    conn = connect()
    try:
        # Serializes the read/modify/write sequence within one workspace only.
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except BaseException:
        try:
            conn.rollback()
        except Exception:
            # A lost remote transaction may also reject rollback. Preserve the
            # original failure; never retry an ambiguous commit automatically.
            pass
        raise
    finally:
        conn.close()


def migrate(connect, workspace, *, target=None):
    """Atomic, restartable migrations with drift detection and workspace binding."""
    if str(uuid.UUID(workspace)) != workspace:
        raise ValueError("Canonical workspace UUID required")
    target = len(MIGRATIONS) if target is None else target
    if type(target) is not int or not 1 <= target <= len(MIGRATIONS):
        raise ValueError("Invalid schema version")
    with transaction(connect) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS proof_migrations (version INTEGER PRIMARY KEY, digest TEXT NOT NULL)")
        applied = dict(conn.execute("SELECT version,digest FROM proof_migrations").fetchall())
        if sorted(applied) != list(range(1, len(applied) + 1)) or len(applied) > target:
            raise ValueError("Unsupported schema version")
        for version, statements in enumerate(MIGRATIONS[:target], 1):
            digest = hashlib.sha256("\n".join(statements).encode()).hexdigest()
            if version in applied:
                if applied[version] != digest:
                    raise ValueError("Migration drift")
                continue
            for statement in statements:
                conn.execute(statement)
            if version == 1:
                conn.execute("INSERT INTO proof_workspace VALUES (1,?)", (workspace,))
            conn.execute("INSERT INTO proof_migrations VALUES (?,?)", (version, digest))
        check_workspace(conn, workspace)


def check_workspace(conn, workspace):
    if conn.execute("SELECT id FROM proof_workspace WHERE singleton=1").fetchone() != (workspace,):
        raise BoundaryDenied("not_found", 404)


class Router:
    """Trusted session resolver and server-owned database registry.

    resolve_session rechecks current membership on EACH call and returns Scope.
    Never construct scopes from request fields. This proof injects fake sessions;
    production OIDC/session and concurrent revocation wiring remain separate work.
    """
    def __init__(self, resolve_session, registry):
        self.resolve_session = resolve_session
        self.registry = dict(registry)

    def call(self, session, operation, *args, **kwargs):
        scope = self.resolve_session(session)
        connect = self.registry.get(scope.tenant_id)
        if connect is None:
            raise BoundaryDenied("not_found", 404)
        if operation not in {"submit", "get"}:
            raise BoundaryDenied("forbidden", 403)
        if operation == "submit":
            scope.require_write()
        return getattr(Store(connect, scope.tenant_id), operation)(*args, **kwargs)


class Store:
    """Worker uses a trusted workspace binding, never an HTTP-supplied endpoint."""
    def __init__(self, connect, workspace):
        self.connect, self.workspace = connect, workspace

    @contextmanager
    def tx(self):
        with transaction(self.connect) as conn:
            check_workspace(conn, self.workspace)
            if conn.execute("SELECT MAX(version) FROM proof_migrations").fetchone()[0] != len(MIGRATIONS):
                raise ValueError("Migration required")
            yield conn

    def submit(self, key, request):
        if not isinstance(key, str) or not 1 <= len(key) <= 128:
            raise ValueError("Invalid idempotency key")
        digest = hash_document(request)
        document = json.dumps(request, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self.tx() as conn:
            row = conn.execute("SELECT id,digest FROM proof_jobs WHERE key=?", (key,)).fetchone()
            if row:
                if row[1] != digest:
                    raise IdempotencyConflict("idempotency_key_conflict")
                return row[0]
            run = str(uuid.uuid4())
            conn.execute("INSERT INTO proof_jobs(id,key,digest,request,state) VALUES (?,?,?,?,'queued')",
                         (run, key, digest, document))
            return run

    def get(self, run):
        with self.tx() as conn:
            row = conn.execute("SELECT state,attempt,result FROM proof_jobs WHERE id=?", (run,)).fetchone()
            if row is None:
                raise BoundaryDenied("not_found", 404)
            return row

    def claim(self, seconds=30, *, run_id=None):
        if type(seconds) is not int or not 1 <= seconds <= 3600:
            raise ValueError("Invalid lease duration")
        with self.tx() as conn:
            row = conn.execute("SELECT id,attempt FROM proof_jobs WHERE state='queued' "
                               "AND (? IS NULL OR id=?) ORDER BY id LIMIT 1", (run_id, run_id)).fetchone()
            if row is None:
                return None
            token = str(uuid.uuid4())
            conn.execute("UPDATE proof_jobs SET state='running',attempt=attempt+1,token=?,"
                         "expires=CAST(strftime('%s','now') AS INTEGER)+? WHERE id=?", (token, seconds, row[0]))
            return row[0], token, row[1] + 1

    def complete(self, run, token, result):
        document = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self.tx() as conn:
            row = conn.execute("SELECT state,token,result FROM proof_jobs WHERE id=?", (run,)).fetchone()
            if row is None or row[1] != token:
                raise LeaseLost("Lease unavailable")
            if row[0] == "completed" and row[2] == document:
                return False
            if row[0] != "running":
                raise LeaseLost("Lease unavailable")
            # Like C3, expiry permits completion until recovery fences the token.
            conn.execute("UPDATE proof_jobs SET state='completed',result=? WHERE id=?", (document, run))
            return True

    def recover(self, *, run_id=None):
        with self.tx() as conn:
            conn.execute("UPDATE proof_jobs SET state=CASE WHEN attempt<2 THEN 'queued' ELSE 'failed' END,"
                         "token=NULL,expires=NULL WHERE state='running' "
                         "AND expires<CAST(strftime('%s','now') AS INTEGER) "
                         "AND (? IS NULL OR id=?)", (run_id, run_id))

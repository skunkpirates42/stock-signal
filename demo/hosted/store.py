"""Authoritative control registry and checksummed workspace schemas (DB-API)."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import secrets
import uuid


class Denied(Exception):
    def __init__(self, code="unauthenticated", status=401):
        self.code, self.status = code, status
        super().__init__(code)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def canonical_id(value):
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise Denied("not_found", 404) from None
    return value


@contextmanager
def transaction(connect):
    conn = connect()
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise Denied("unavailable", 503)
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except BaseException:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


CONTROL = (
    "CREATE TABLE users (id TEXT PRIMARY KEY, issuer TEXT NOT NULL, subject TEXT NOT NULL, UNIQUE(issuer,subject))",
    "CREATE TABLE workspaces (id TEXT PRIMARY KEY, personal_user TEXT NOT NULL UNIQUE REFERENCES users(id), state TEXT NOT NULL CHECK(state IN ('reserved','initializing','ready','failed')), database_name TEXT NOT NULL UNIQUE, endpoint TEXT, secret_ref TEXT, schema_version INTEGER NOT NULL DEFAULT 0, failure_code TEXT)",
    "CREATE TABLE memberships (user_id TEXT NOT NULL REFERENCES users(id), workspace_id TEXT NOT NULL REFERENCES workspaces(id), role TEXT NOT NULL CHECK(role IN ('owner','operator','viewer')), active INTEGER NOT NULL CHECK(active IN (0,1)), PRIMARY KEY(user_id,workspace_id))",
    "CREATE TABLE challenges (id_hash TEXT PRIMARY KEY, nonce TEXT NOT NULL, expires INTEGER NOT NULL)",
    "CREATE TABLE sessions (id_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), csrf_hash TEXT NOT NULL, expires INTEGER NOT NULL)",
    "CREATE TABLE rate_limits (key TEXT NOT NULL, bucket INTEGER NOT NULL, count INTEGER NOT NULL, PRIMARY KEY(key,bucket))",
)
WORKSPACE = (
    "CREATE TABLE workspace_binding (singleton INTEGER PRIMARY KEY CHECK(singleton=1), workspace_id TEXT NOT NULL UNIQUE)",
    "CREATE TABLE runs (id TEXT PRIMARY KEY)",
    "CREATE TABLE results (id TEXT PRIMARY KEY, run_id TEXT NOT NULL UNIQUE REFERENCES runs(id))",
    "CREATE TABLE result_artifacts (id TEXT PRIMARY KEY, result_id TEXT NOT NULL REFERENCES results(id))",
)


def migrate(connect, statements, workspace_id=None):
    """C2 version 1; drift, unknown versions, and wrong bindings fail closed."""
    checksum = digest("\n".join(statements))
    with transaction(connect) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, checksum TEXT NOT NULL)")
        applied = conn.execute("SELECT version,checksum FROM schema_migrations ORDER BY version").fetchall()
        if applied and applied != [(1, checksum)]:
            raise Denied("schema_mismatch", 503)
        if not applied:
            for statement in statements:
                conn.execute(statement)
            if workspace_id is not None:
                conn.execute("INSERT INTO workspace_binding VALUES (1,?)", (canonical_id(workspace_id),))
            conn.execute("INSERT INTO schema_migrations VALUES (1,?)", (checksum,))
        if workspace_id is not None:
            check_binding(conn, workspace_id)


def check_binding(conn, workspace_id):
    if conn.execute("SELECT workspace_id FROM workspace_binding WHERE singleton=1").fetchone() != (workspace_id,):
        raise Denied("unavailable", 503)
    if conn.execute("SELECT version,checksum FROM schema_migrations ORDER BY version").fetchall() != [(1, digest("\n".join(WORKSPACE)))]:
        raise Denied("schema_mismatch", 503)


def now(conn):
    return conn.execute("SELECT CAST(strftime('%s','now') AS INTEGER)").fetchone()[0]


def limit(conn, key, maximum):
    bucket = now(conn) // 60
    conn.execute("DELETE FROM rate_limits WHERE bucket<?", (bucket - 1,))
    conn.execute("INSERT INTO rate_limits VALUES (?,?,1) ON CONFLICT(key,bucket) DO UPDATE SET count=count+1", (key, bucket))
    return conn.execute("SELECT count FROM rate_limits WHERE key=? AND bucket=?", (key, bucket)).fetchone()[0] <= maximum


@dataclass(frozen=True)
class Scope:
    user_id: str
    tenant_id: str
    role: str


class Control:
    def __init__(self, connect):
        self.connect = connect

    def challenge(self):
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with transaction(self.connect) as conn:
            conn.execute("DELETE FROM challenges WHERE expires<=?", (now(conn),))
            # Global pre-auth budget prevents unbounded challenge/JWKS work.
            allowed = limit(conn, "login", 60)
            if allowed:
                conn.execute("INSERT INTO challenges VALUES (?,?,?)", (digest(state), nonce, now(conn) + 300))
        if not allowed:
            raise Denied("rate_limited", 429)
        return state, nonce

    def login(self, state, token, verifier):
        # Consume even failed challenges; the browser must start a fresh login.
        with transaction(self.connect) as conn:
            row = conn.execute("SELECT nonce,expires FROM challenges WHERE id_hash=?", (digest(state),)).fetchone()
            conn.execute("DELETE FROM challenges WHERE id_hash=?", (digest(state),))
            valid = row is not None and row[1] > now(conn)
        if not valid:
            raise Denied()
        identity = verifier.verify(token, row[0])
        session, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with transaction(self.connect) as conn:
            conn.execute("INSERT INTO users VALUES (?,?,?) ON CONFLICT(issuer,subject) DO NOTHING",
                         (str(uuid.uuid4()), identity.issuer, identity.subject))
            user = conn.execute("SELECT id FROM users WHERE issuer=? AND subject=?", (identity.issuer, identity.subject)).fetchone()[0]
            conn.execute("DELETE FROM sessions WHERE expires<=?", (now(conn),))
            conn.execute("INSERT INTO sessions VALUES (?,?,?,?)", (digest(session), user, digest(csrf), now(conn) + 3600))
        return session, csrf, user

    def reserve(self, user):
        canonical_id(user)
        with transaction(self.connect) as conn:
            row = conn.execute("SELECT id FROM workspaces WHERE personal_user=?", (user,)).fetchone()
            if row:
                return row[0]
            workspace = str(uuid.uuid4())
            conn.execute("INSERT INTO workspaces(id,personal_user,state,database_name) VALUES (?,?,'reserved',?)",
                         (workspace, user, "ws-" + workspace.replace("-", "")))
            conn.execute("INSERT INTO memberships VALUES (?,?,'owner',1)", (user, workspace))
            return workspace

    def revoke(self, user, workspace):
        """Trusted administrative action, serialized with EVERY boundary operation."""
        with transaction(self.connect) as conn:
            conn.execute("UPDATE memberships SET active=0 WHERE user_id=? AND workspace_id=?", (user, workspace))

    def logout(self, session):
        with transaction(self.connect) as conn:
            conn.execute("DELETE FROM sessions WHERE id_hash=?", (digest(session),))

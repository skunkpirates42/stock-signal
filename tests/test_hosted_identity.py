"""Offline C2 crypto and HTTP boundary tests. No provider or broker calls."""
from contextlib import contextmanager
import json
import sqlite3
import time
import uuid

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
import pytest

from demo.hosted_api import create_hosted_app
from demo.hosted_identity import BoundaryDenied, OIDCVerifier, PostgresIdentity, Scope


ISSUER = "https://identity.example.test"
ORIGIN = "https://demo.example.test"


@pytest.fixture(scope="module")
def keys():
    return [rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2)]


@pytest.fixture
def provider(keys, monkeypatch):
    verifier = OIDCVerifier(ISSUER, "demo-client", ISSUER + "/jwks")
    document = {"keys": []}
    def publish(index):
        key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(keys[index].public_key()))
        key.update(kid=str(index), use="sig", alg="RS256")
        document["keys"] = [key]
    publish(0)
    monkeypatch.setattr(verifier.keys, "fetch_data", lambda: document.copy())
    def token(index=0, **updates):
        claims = dict(iss=ISSUER, aud="demo-client", sub="subject-a", nonce="trusted-nonce",
                      iat=int(time.time()) - 1, exp=int(time.time()) + 600)
        claims.update(updates)
        return jwt.encode(claims, keys[index], algorithm="RS256", headers={"kid": str(index)})
    return verifier, token, publish


def test_signature_and_key_rotation(provider):
    verifier, token, publish = provider
    assert verifier.verify(token(), "trusted-nonce")["sub"] == "subject-a"
    publish(1)
    assert verifier.verify(token(1), "trusted-nonce")["sub"] == "subject-a"
    # The new JWKS replaced the old one; a removed key cannot survive indefinitely.
    with pytest.raises(BoundaryDenied):
        verifier.verify(token(), "trusted-nonce")


@pytest.mark.parametrize("changes", [
    {"iss": "https://attacker.test"}, {"aud": "wrong"}, {"exp": 1},
    {"iat": 9999999999}, {"nonce": "attacker-nonce"}, {"sub": ""},
    {"aud": ["demo-client", "other"]}, {"azp": "other"},
])
def test_invalid_claims_fail_closed(provider, changes):
    verifier, token, _ = provider
    with pytest.raises(BoundaryDenied, match="^unauthenticated$"):
        verifier.verify(token(**changes), "trusted-nonce")


def test_malformed_missing_claims_signature_and_algorithm(provider, keys):
    verifier, token, _ = provider
    claims = jwt.decode(token(), options={"verify_signature": False})
    without_exp = dict(claims)
    del without_exp["exp"]
    invalid = [None, "garbage", "x" * 16385,
               jwt.encode(without_exp, keys[0], algorithm="RS256", headers={"kid": "0"}),
               jwt.encode(claims, keys[1], algorithm="RS256", headers={"kid": "0"}),
               jwt.encode(claims, "fake-test-secret-at-least-32-bytes", algorithm="HS256", headers={"kid": "0"})]
    for value in invalid:
        with pytest.raises(BoundaryDenied):
            verifier.verify(value, "trusted-nonce")
    with pytest.raises(BoundaryDenied):
        verifier.verify(token(), None)


def test_jwks_failure_is_sanitized(provider, monkeypatch):
    verifier, token, _ = provider
    def unavailable():
        raise jwt.PyJWKClientConnectionError("private-secret /private/path")
    monkeypatch.setattr(verifier.keys, "fetch_data", unavailable)
    with pytest.raises(BoundaryDenied, match="^unauthenticated$"):
        verifier.verify(token(), "trusted-nonce")


class OfflineIdentity:
    """Fake sessions/memberships; actual C2 resource lookup runs against fixture SQL."""
    authorize_resources = PostgresIdentity.authorize_resources

    def __init__(self):
        self.a = Scope(str(uuid.uuid4()), str(uuid.uuid4()), "operator")
        self.b = Scope(str(uuid.uuid4()), str(uuid.uuid4()), "owner")
        self.viewer = Scope(str(uuid.uuid4()), self.a.tenant_id, "viewer")
        self.sessions = {"a": self.a, "b": self.b, "viewer": self.viewer}
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE hosted_resources (tenant_id,id,kind,parent_id)")
        self.resources = {}
        for label, scope in (("a", self.a), ("b", self.b)):
            run, result, artifact = (str(uuid.uuid4()) for _ in range(3))
            self.resources[label] = (run, result, artifact)
            self.conn.executemany("INSERT INTO hosted_resources VALUES (?,?,?,?)", [
                (scope.tenant_id, run, "run", None),
                (scope.tenant_id, result, "result", run),
                (scope.tenant_id, artifact, "artifact", run)])

    def authenticate(self, session, csrf=None):
        if session not in self.sessions:
            raise BoundaryDenied()
        if csrf is not None and csrf != "fixture-csrf":
            raise BoundaryDenied("csrf_rejected", 403)
        scope = self.sessions[session]
        if scope is None:
            raise BoundaryDenied("tenant_unavailable", 403)
        return scope

    @contextmanager
    def transaction(self, scope):
        yield self

    def execute(self, statement, params):
        return self.conn.execute(statement.replace("%s", "?"), params)


class OfflineLimiter:
    def __init__(self):
        self.counts = {}
        self.user_limit, self.tenant_limit = 100, 100

    def check(self, scope):
        for key, limit in ((scope.user_id, self.user_limit), (scope.tenant_id, self.tenant_limit)):
            self.counts[key] = self.counts.get(key, 0) + 1
            if self.counts[key] > limit:
                raise BoundaryDenied("rate_limited", 429)


class OfflineService:
    def __init__(self):
        self.calls = []

    def handle(self, conn, scope, operation, ids, query, body):
        self.calls.append((scope, operation))
        if operation.endswith("artifact"):
            return b"fixture", "text/plain"
        return {"schema_version": 1, "data": {"tenant": scope.tenant_id}, "warnings": []}


@pytest.fixture
def hosted():
    identity, limiter, service = OfflineIdentity(), OfflineLimiter(), OfflineService()
    app = create_hosted_app(identity=identity, limiter=limiter, service=service, origin=ORIGIN)
    app.testing = True
    client = app.test_client()
    client.set_cookie("__Host-demo-session", "a", domain="demo.example.test")
    def call(path="runs", method="GET", **kwargs):
        return client.open("/api/demo/v1/" + path, method=method, base_url=ORIGIN, **kwargs)
    return identity, limiter, service, client, call


def test_owned_status_result_artifact_and_role_reads(hosted):
    identity, _, service, client, call = hosted
    run, result, artifact = identity.resources["a"]
    for path in ("runs", "research", "runs/" + run, "results/" + result,
                 "runs/" + run + "/artifacts/" + artifact, "runs?cursor=" + run):
        assert call(path).status_code == 200
    client.set_cookie("__Host-demo-session", "viewer", domain="demo.example.test")
    assert call("runs/" + run).status_code == 200
    assert all(scope.tenant_id == identity.a.tenant_id for scope, _ in service.calls)


def test_cross_tenant_ids_cursors_and_artifact_parent_fail_before_service(hosted):
    identity, _, service, _, call = hosted
    run, result, artifact = identity.resources["b"]
    own_run = identity.resources["a"][0]
    for path in ("runs/" + run, "results/" + result, "runs?cursor=" + run,
                 "research?cursor=" + result, "runs/" + own_run + "/artifacts/" + artifact,
                 "runs/" + str(uuid.uuid4())):
        response = call(path)
        assert response.status_code == 404
        assert response.json["error"]["code"] == "not_found"
    assert call("runs/" + run + "/cancel", method="POST", json={},
                headers={"Origin": ORIGIN, "X-CSRF-Token": "fixture-csrf"}).status_code == 404
    assert service.calls == []


def test_missing_session_and_missing_or_ambiguous_membership_fail_closed(hosted):
    identity, _, service, client, call = hosted
    client.delete_cookie("__Host-demo-session", domain="demo.example.test")
    assert call().status_code == 401
    client.set_cookie("__Host-demo-session", "a", domain="demo.example.test")
    identity.sessions["a"] = None
    assert call().status_code == 403
    assert service.calls == []


def test_csrf_cors_roles_and_override_rejections(hosted):
    identity, _, service, client, call = hosted
    path = "runs/" + identity.resources["a"][0] + "/cancel"
    for headers in ({}, {"Origin": "https://attacker.test", "X-CSRF-Token": "fixture-csrf"},
                    {"Origin": ORIGIN}, {"Origin": ORIGIN, "X-CSRF-Token": "wrong"}):
        assert call(path, method="POST", json={}, headers=headers).status_code == 403
    headers = {"Origin": ORIGIN, "X-CSRF-Token": "fixture-csrf"}
    assert call(path, method="POST", json={"tenant_id": identity.b.tenant_id}, headers=headers).status_code == 400
    for query in ("tenant_id=other", "cache_key=other", "cursor=x&cursor=y"):
        assert call("runs?" + query).status_code == 400
    assert call(headers={"X-Tenant-ID": identity.b.tenant_id}).status_code == 400
    preflight = call(method="OPTIONS", headers={"Origin": "https://attacker.test"})
    assert preflight.status_code == 405
    assert "Access-Control-Allow-Origin" not in preflight.headers
    assert service.calls == []
    client.set_cookie("__Host-demo-session", "viewer", domain="demo.example.test")
    assert call(path, method="POST", json={}, headers=headers).status_code == 403
    client.set_cookie("__Host-demo-session", "a", domain="demo.example.test")
    assert call(path, method="POST", json={}, headers=headers).status_code == 200


def test_limits_cache_and_sanitized_failures(hosted, monkeypatch, caplog):
    identity, limiter, service, client, call = hosted
    assert identity.a.cache_key("run", "x") != identity.b.cache_key("run", "x")
    response = call()
    assert response.headers["Cache-Control"] == "private, no-store"
    limiter.user_limit = 1
    assert call().status_code == 429
    limiter.user_limit = 100
    limiter.tenant_limit = 1
    client.set_cookie("__Host-demo-session", "viewer", domain="demo.example.test")
    assert call().status_code == 429
    limiter.tenant_limit = 100
    def broken(*args):
        raise RuntimeError("private-secret /private/path")
    monkeypatch.setattr(service, "handle", broken)
    response = call()
    assert response.status_code == 503
    assert "private-secret" not in response.get_data(as_text=True) + caplog.text
    client.set_cookie("__Host-demo-session", "a", domain="demo.example.test")
    oversized = call("runs", method="POST", data="x" * 4097, content_type="application/json",
                     headers={"Origin": ORIGIN, "X-CSRF-Token": "fixture-csrf"})
    assert oversized.status_code == 413


@pytest.fixture
def identity_store():
    """Exercise repository behavior offline; this is not a PostgreSQL RLS test."""
    db = sqlite3.connect(":memory:")
    db.executescript('''
      CREATE TABLE hosted_login_challenges (id_hash PRIMARY KEY,nonce,expires_at);
      CREATE TABLE hosted_users (id PRIMARY KEY,issuer,subject,UNIQUE(issuer,subject));
      CREATE TABLE hosted_sessions (id_hash PRIMARY KEY,user_id,csrf_hash,expires_at);
      CREATE TABLE hosted_memberships (tenant_id,user_id,role);
      CREATE TABLE hosted_rate_buckets (kind,identity,bucket,count,PRIMARY KEY(kind,identity,bucket));
    ''')
    db.create_function("clock_timestamp", 0, time.time)
    db.create_function("statement_timestamp", 0, time.time)
    db.create_function("to_timestamp", 1, lambda value: value)
    db.create_function("date_trunc", 2, lambda unit, value: int(value) // 60)
    db.create_function("set_config", 3, lambda key, value, local: value)
    db.create_function("pg_advisory_xact_lock_shared", 2, lambda namespace, key: None)
    class Connection:
        statements = []

        def __enter__(self):
            return self
        def __exit__(self, exc_type, *args):
            db.rollback() if exc_type else db.commit()
        def execute(self, sql, params=()):
            self.statements.append(sql)
            # A SELECT-only membership role cannot run PostgreSQL row locks.
            if "FOR SHARE" in sql or "FOR UPDATE" in sql:
                raise PermissionError("membership role is SELECT-only")
            if sql == "SET TRANSACTION ISOLATION LEVEL READ COMMITTED":
                return db.execute("SELECT 1")
            sql = (sql.replace("%s", "?").replace("interval '5 minutes'", "300")
                   .replace("interval '1 hour'", "3600").replace("LEAST(", "min(")
                   .replace("pg_catalog.", ""))
            return db.execute(sql, params)
    return PostgresIdentity(Connection, data_connect=Connection), db, Connection


def test_first_login_stable_identity_session_expiry_and_nonce_consumption(identity_store, provider):
    store, db, _ = identity_store
    verifier, token, _ = provider
    challenge, nonce = store.begin_login()
    session, csrf = store.finish_login(verifier, challenge, token(nonce=nonce))
    user_id = db.execute("SELECT id FROM hosted_users").fetchone()[0]
    with pytest.raises(BoundaryDenied):
        store.authenticate(session)  # first login does not invent a membership
    tenant_id = str(uuid.uuid4())
    db.execute("INSERT INTO hosted_memberships VALUES (?,?,?)", (tenant_id, user_id, "owner"))
    db.commit()
    scope = store.authenticate(session, csrf)
    assert (scope.user_id, scope.tenant_id, scope.role) == (user_id, tenant_id, "owner")
    with pytest.raises(BoundaryDenied):
        store.finish_login(verifier, challenge, token(nonce=nonce))
    next_challenge, next_nonce = store.begin_login()
    next_session, _ = store.finish_login(verifier, next_challenge, token(nonce=next_nonce))
    assert store.authenticate(next_session).user_id == user_id
    assert db.execute("SELECT count(*) FROM hosted_users").fetchone()[0] == 1
    with pytest.raises(BoundaryDenied):
        store.authenticate(session, "wrong-csrf")
    store.revoke(session)
    with pytest.raises(BoundaryDenied):
        store.authenticate(session)
    db.execute("UPDATE hosted_sessions SET expires_at=0")
    db.commit()
    with pytest.raises(BoundaryDenied):
        store.authenticate(next_session)


def test_membership_rechecked_and_ambiguous_tenants_denied(identity_store, provider):
    store, db, _ = identity_store
    verifier, token, _ = provider
    challenge, nonce = store.begin_login()
    session, _ = store.finish_login(verifier, challenge, token(nonce=nonce))
    user = db.execute("SELECT id FROM hosted_users").fetchone()[0]
    db.execute("INSERT INTO hosted_memberships VALUES (?,?,?)", (str(uuid.uuid4()), user, "operator"))
    db.commit()
    scope = store.authenticate(session)
    db.execute("UPDATE hosted_memberships SET role='viewer'")
    db.commit()
    with pytest.raises(BoundaryDenied):
        with store.transaction(scope):
            pytest.fail("revoked role reached operation")
    db.execute("INSERT INTO hosted_memberships VALUES (?,?,?)", (str(uuid.uuid4()), user, "owner"))
    db.commit()
    with pytest.raises(BoundaryDenied):
        store.authenticate(session)
    db.execute("DELETE FROM hosted_memberships")
    db.commit()
    with pytest.raises(BoundaryDenied):
        store.authenticate(session)


def test_durable_rate_counters_share_user_and_tenant_dimensions(identity_store):
    from demo.hosted_identity import PostgresRateLimit
    _, db, connect = identity_store
    tenant = str(uuid.uuid4())
    a, b = (Scope(str(uuid.uuid4()), tenant, "operator") for _ in range(2))
    limiter = PostgresRateLimit(connect, user_limit=1, tenant_limit=2)
    limiter.check(a)
    with pytest.raises(BoundaryDenied, match="rate_limited"):
        limiter.check(a)
    # Rejections still consume the shared bucket, including across limiter instances.
    other_process = PostgresRateLimit(connect, user_limit=10, tenant_limit=2)
    with pytest.raises(BoundaryDenied, match="rate_limited"):
        other_process.check(b)
    assert db.execute("SELECT count FROM hosted_rate_buckets WHERE kind='tenant'").fetchone()[0] == 3


def test_authorized_transaction_uses_read_only_membership_check(identity_store):
    store, db, connection = identity_store
    scope = Scope(str(uuid.uuid4()), str(uuid.uuid4()), "operator")
    db.execute("INSERT INTO hosted_memberships VALUES (?,?,?)",
               (scope.tenant_id, scope.user_id, scope.role))
    db.commit()
    with store.transaction(scope) as conn:
        assert conn.execute("SELECT 42").fetchone()[0] == 42
    statements = connection.statements
    assert statements[0] == "SET TRANSACTION ISOLATION LEVEL READ COMMITTED"
    assert statements[1] == "SELECT pg_catalog.pg_advisory_xact_lock_shared(1937010547, 1)"
    assert statements[4] == "SELECT tenant_id,role FROM hosted_memberships WHERE user_id=%s"
    assert all("FOR SHARE" not in sql and "FOR UPDATE" not in sql for sql in statements)


def test_revocation_committed_while_waiting_for_lock_is_rechecked(identity_store):
    store, db, connection = identity_store
    scope = Scope(str(uuid.uuid4()), str(uuid.uuid4()), "operator")
    db.execute("INSERT INTO hosted_memberships VALUES (?,?,?)",
               (scope.tenant_id, scope.user_id, scope.role))
    db.commit()
    class RevocationWins(connection):
        def execute(self, sql, params=()):
            if "pg_advisory_xact_lock_shared" in sql:
                # Simulate a writer committing while the request waits for its lock.
                db.execute("UPDATE hosted_memberships SET role='viewer'")
                db.commit()
            return super().execute(sql, params)
    store.data_connect = RevocationWins
    with pytest.raises(BoundaryDenied, match="tenant_unavailable"):
        with store.transaction(scope):
            pytest.fail("revoked operation reached service")


def test_migration_guards_every_membership_change_with_matching_lock():
    from pathlib import Path
    migration = (Path(__file__).parents[1] / "demo/migrations/001_hosted_identity.sql").read_text()
    assert "pg_catalog.pg_advisory_xact_lock(1937010547, 1)" in migration
    assert "BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON hosted_memberships" in migration
    assert "FOR EACH STATEMENT EXECUTE FUNCTION hosted_membership_write_lock()" in migration
    assert "LANGUAGE plpgsql SET search_path = pg_catalog" in migration

"""Synthetic-only tests for C2; no remote databases or real identities."""
import json
import multiprocessing
import sqlite3
import time
import uuid
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from demo.hosted.api import LOGIN, SESSION, create_hosted_app
from demo.hosted.boundary import Boundary
from demo.hosted.identity import Identity, OIDCVerifier
from demo.hosted.provisioning import Provisioner, TursoPlatform
from demo.hosted.store import CONTROL, WORKSPACE, Control, Denied, Scope, digest, migrate, transaction

ORIGIN = "https://demo.example"
ISSUER = "https://identity.example"


class FakeVerifier:
    def verify(self, token, nonce):
        if token != "synthetic":
            raise Denied()
        return Identity(ISSUER, "synthetic-subject")


class SecretStore:
    def __init__(self):
        self.values = {}

    def put(self, ref, value):
        self.values[ref] = value

    def get(self, ref):
        return self.values[ref]


class Platform:
    def __init__(self):
        self.names = set()

    def ensure_database(self, name):
        self.names.add(name)
        return "libsql://" + name + ".turso.io"

    def database_token(self, name):
        return "synthetic-database-token"


@pytest.fixture
def system(tmp_path):
    control_path = tmp_path / "control.db"
    connect = lambda: sqlite3.connect(control_path, isolation_level=None, timeout=5)
    migrate(connect, CONTROL)
    control = Control(connect)
    platform, secrets = Platform(), SecretStore()
    databases = {}

    def connections(endpoint, ref):
        secrets.get(ref)
        return sqlite3.connect(databases[endpoint], isolation_level=None, timeout=5)

    def new_user(subject):
        user = str(uuid.uuid4())
        with transaction(connect) as conn:
            conn.execute("INSERT INTO users VALUES (?,?,?)", (user, ISSUER, subject))
        workspace = control.reserve(user)
        name = "ws-" + workspace.replace("-", "")
        endpoint = "libsql://" + name + ".turso.io"
        databases[endpoint] = tmp_path / (workspace + ".db")
        Provisioner(control, platform, secrets, connections).provision(workspace)
        session, csrf = "session-" + subject, "csrf-" + subject
        with transaction(connect) as conn:
            conn.execute("INSERT INTO sessions VALUES (?,?,?,?)", (digest(session), user, digest(csrf), int(time.time()) + 3600))
        return Scope(user, workspace, "owner"), session, csrf

    a, sa, ca = new_user("a")
    b, sb, cb = new_user("b")
    boundary = Boundary(control, connections, b"k" * 32)
    return SimpleNamespace(control=control, connect=connect, connections=connections,
                           databases=databases, platform=platform, secrets=secrets,
                           a=a, b=b, sa=sa, sb=sb, ca=ca, cb=cb, boundary=boundary)


def test_oidc_validation_and_rotation():
    keys = [rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2)]
    documents = [{"keys": [dict(json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())), kid=str(i), alg="RS256", use="sig")]} for i, key in enumerate(keys)]

    class JWKS(jwt.PyJWKClient):
        def __init__(self):
            super().__init__(ISSUER + "/jwks", cache_keys=False, lifespan=60)
            self.current, self.fetches = 0, 0

        def fetch_data(self):
            self.fetches += 1
            data = documents[self.current]
            self.jwk_set_cache.put(data)
            return data

    client = JWKS()
    verifier = OIDCVerifier(ISSUER, "demo-client", ISSUER + "/jwks", jwks=client)
    claims = {"iss": ISSUER, "sub": "subject", "aud": "demo-client", "iat": int(time.time()), "exp": int(time.time()) + 300, "nonce": "expected"}

    def token(changes=None, key=0, algorithm="RS256"):
        return jwt.encode(dict(claims, **(changes or {})), keys[key] if algorithm == "RS256" else "f" * 32, algorithm=algorithm, headers={"kid": str(key)})

    assert verifier.verify(token(), "expected").subject == "subject"
    assert client.fetches == 1
    client.current = 1
    assert verifier.verify(token(key=1), "expected").subject == "subject"
    assert client.fetches == 2
    client.jwk_set_cache.put(None)  # Retired key is rejected after cache expiry.
    bad = ["", "garbage", token({"exp": 1}, key=1), token({"aud": "other"}, key=1), token({"iss": "https://other.example"}, key=1), token({"nonce": "other"}, key=1), token({"iat": int(time.time()) + 100}, key=1), token(algorithm="HS256"), token({"aud": ["demo-client", "other"]}, key=1)]
    for value in bad:
        with pytest.raises(Denied):
            verifier.verify(value, "expected")
    with pytest.raises(Denied):
        verifier.verify(token(key=0), "expected")
    forged = jwt.encode(claims, keys[0], algorithm="RS256", headers={"kid": "1"})
    with pytest.raises(Denied):
        verifier.verify(forged, "expected")


def test_login_single_use_nonce_and_stable_subject(system):
    state, _ = system.control.challenge()
    first = system.control.login(state, "synthetic", FakeVerifier())
    with pytest.raises(Denied):
        system.control.login(state, "synthetic", FakeVerifier())
    state, _ = system.control.challenge()
    second = system.control.login(state, "synthetic", FakeVerifier())
    assert first[2] == second[2]
    assert first[0] != second[0]
    workspace = system.control.reserve(first[2])
    assert system.control.reserve(first[2]) == workspace
    with transaction(system.connect) as conn:
        assert conn.execute("SELECT state FROM workspaces WHERE id=?", (workspace,)).fetchone() == ("reserved",)
    state, _ = system.control.challenge()
    with pytest.raises(Denied):
        system.control.login(state, "bad", FakeVerifier())
    with pytest.raises(Denied):
        system.control.login(state, "synthetic", FakeVerifier())


@pytest.mark.parametrize("operation", ["submit", "status", "cancel", "result", "artifact", "list"])
def test_every_operation_uses_membership_and_registry(system, operation):
    seen = []
    assert system.boundary.call(system.sa, operation, lambda conn, scope: seen.append(scope) or "ok", csrf=system.ca) == "ok"
    assert seen == [system.a]
    system.control.revoke(system.a.user_id, system.a.tenant_id)
    with pytest.raises(Denied):
        system.boundary.call(system.sa, operation, lambda *_: pytest.fail("revoked handler invoked"), csrf=system.ca)


@pytest.mark.parametrize("fault", ["expired", "ambiguous", "wrong_binding", "not_ready", "missing", "checksum"])
def test_registry_and_session_faults_fail_closed(system, fault):
    with transaction(system.connect) as conn:
        if fault == "expired":
            conn.execute("UPDATE sessions SET expires=0 WHERE id_hash=?", (digest(system.sa),))
        elif fault == "ambiguous":
            conn.execute("INSERT INTO memberships VALUES (?,?,'viewer',1)", (system.a.user_id, system.b.tenant_id))
        elif fault == "wrong_binding":
            endpoint, ref = conn.execute("SELECT endpoint,secret_ref FROM workspaces WHERE id=?", (system.b.tenant_id,)).fetchone()
            conn.execute("UPDATE workspaces SET endpoint=?,secret_ref=? WHERE id=?", (endpoint, ref, system.a.tenant_id))
        elif fault == "not_ready":
            conn.execute("UPDATE workspaces SET state='initializing' WHERE id=?", (system.a.tenant_id,))
        elif fault == "missing":
            conn.execute("UPDATE workspaces SET secret_ref=NULL WHERE id=?", (system.a.tenant_id,))
    if fault == "checksum":
        endpoint = next(endpoint for endpoint in system.databases if system.a.tenant_id.replace("-", "") in endpoint)
        with transaction(lambda: system.connections(endpoint, "workspaces/" + system.a.tenant_id + "/database")) as conn:
            conn.execute("UPDATE schema_migrations SET checksum='tampered'")
    with pytest.raises(Denied):
        system.boundary.call(system.sa, "status", lambda *_: pytest.fail("untrusted handler invoked"))


def test_roles_cursors_cache_keys_and_parent_foreign_keys(system):
    with transaction(system.connect) as conn:
        conn.execute("UPDATE memberships SET role='viewer' WHERE user_id=?", (system.a.user_id,))
    assert system.boundary.call(system.sa, "status", lambda _, scope: scope.role) == "viewer"
    with pytest.raises(Denied):
        system.boundary.call(system.sa, "cancel", lambda *_: None, csrf=system.ca)
    with transaction(system.connect) as conn:
        conn.execute("UPDATE memberships SET role='operator' WHERE user_id=?", (system.a.user_id,))
    assert system.boundary.call(system.sa, "submit", lambda _, scope: scope.role, csrf=system.ca) == "operator"
    cursor = system.boundary.cursor(system.a, "position")
    assert system.boundary.read_cursor(system.a, cursor) == "position"
    for scope, value in [(system.b, cursor), (system.a, cursor + "bad")]:
        with pytest.raises(Denied):
            system.boundary.read_cursor(scope, value)
    assert system.boundary.cache_key(system.a, "status", "run") != system.boundary.cache_key(system.b, "status", "run")
    with pytest.raises(sqlite3.IntegrityError):
        system.boundary.call(system.sa, "submit", lambda conn, _: conn.execute("INSERT INTO result_artifacts VALUES ('a','missing')"), csrf=system.ca)


def _operation_process(control_path, workspace_path, session, entered, release, results):
    control = Control(lambda: sqlite3.connect(control_path, isolation_level=None, timeout=5))
    boundary = Boundary(control, lambda *_: sqlite3.connect(workspace_path, isolation_level=None), b"k" * 32)
    def handler(conn, _):
        entered.set()
        assert release.wait(5)
        conn.execute("INSERT INTO runs VALUES ('in-flight')")
        return "materialized"
    results.put(boundary.call(session, "status", handler))


def _revoke_process(control_path, user, workspace, started, revoked, pending):
    started.set()
    try:
        Control(lambda: sqlite3.connect(control_path, isolation_level=None, timeout=5)).revoke(user, workspace)
    except Denied as exc:
        assert exc.code == "revocation_pending"
        pending.set()
    else:
        revoked.set()


def test_revocation_blocks_new_admissions_and_waits_for_known_outcome(system):
    context = multiprocessing.get_context("spawn")
    entered, release, started, revoked, pending = [context.Event() for _ in range(5)]
    results = context.Queue()
    with transaction(system.connect) as conn:
        endpoint = conn.execute("SELECT endpoint FROM workspaces WHERE id=?", (system.a.tenant_id,)).fetchone()[0]
        control_path = conn.execute("PRAGMA database_list").fetchone()[2]
    operation = context.Process(target=_operation_process, args=(control_path, system.databases[endpoint], system.sa, entered, release, results))
    revocation = context.Process(target=_revoke_process, args=(control_path, system.a.user_id, system.a.tenant_id, started, revoked, pending))
    try:
        operation.start()
        assert entered.wait(5)
        revocation.start()
        assert started.wait(5)
        assert pending.wait(5)
        assert not revoked.is_set()
        with pytest.raises(Denied):
            system.boundary.call(system.sa, "status", lambda *_: pytest.fail("new admission after revoke"))
        release.set()
        operation.join(5)
        revocation.join(5)
        assert operation.exitcode == revocation.exitcode == 0
        system.control.revoke(system.a.user_id, system.a.tenant_id)
        assert not revoked.is_set()  # First revocation reported pending only.
        assert results.get(timeout=2) == "materialized"
        with pytest.raises(Denied):
            system.boundary.call(system.sa, "status", lambda *_: pytest.fail("late handler"))
    finally:
        release.set()
        for process in (operation, revocation):
            if process.pid and process.is_alive():
                process.terminate()
                process.join()


def app_client(system, handlers=None):
    app = create_hosted_app(system.control, FakeVerifier(), system.boundary, origin=ORIGIN, handlers=handlers)
    client = app.test_client()
    client.set_cookie(SESSION, system.sa, domain="demo.example", secure=True)
    return client


def send(client, path, method="GET", **kwargs):
    return client.open("/api/hosted/v1" + path, method=method, base_url=ORIGIN, **kwargs)


def test_http_login_binding_cookie_and_logout(system):
    client = app_client(system)
    headers = {"Origin": ORIGIN}
    challenge = send(client, "/auth/challenge", "POST", json={}, headers=headers)
    data = challenge.get_json()["data"]
    assert "Secure" in challenge.headers["Set-Cookie"]
    assert "HttpOnly" in challenge.headers["Set-Cookie"]
    assert "SameSite=Strict" in challenge.headers["Set-Cookie"]
    login = send(client, "/auth/login", "POST", json={"state": data["state"], "id_token": "synthetic"}, headers=headers)
    assert login.status_code == 200
    assert "secret" not in login.get_data(as_text=True)
    assert send(client, "/workspace").status_code == 503  # Reserved, not provisioned.
    assert send(client, "/auth/login", "POST", json={"state": data["state"], "id_token": "synthetic"}, headers=headers).status_code == 401
    assert send(client, "/auth/logout", "POST", json={}, headers=headers).status_code == 200
    assert send(client, "/workspace").status_code == 401


@pytest.mark.parametrize("headers,expected", [({}, 403), ({"Origin": "https://evil.example"}, 403), ({"Origin": ORIGIN}, 403), ({"Origin": ORIGIN, "X-CSRF-Token": "wrong"}, 403)])
def test_http_csrf(system, headers, expected):
    assert send(app_client(system), "/runs/" + str(uuid.uuid4()) + "/cancel", "POST", json={}, headers=headers).status_code == expected


@pytest.mark.parametrize("method,path,headers", [("GET", "/workspace", {"Origin": "https://evil.example"}), ("OPTIONS", "/runs", {"Origin": "https://evil.example"}), ("GET", "/workspace", {"Sec-Fetch-Site": "cross-site"}), ("GET", "/workspace?tenant_id=other", {}), ("GET", "/workspace?cache_key=other", {}), ("GET", "/workspace", {"Authorization": "Bearer malformed"})])
def test_http_origin_and_override_denial(system, method, path, headers):
    response = send(app_client(system), path, method, headers=headers)
    assert response.status_code in {400, 403}
    assert "Access-Control-Allow-Origin" not in response.headers


def test_http_body_scope_and_errors_are_safe(system):
    client = app_client(system, {"status": lambda *_: (_ for _ in ()).throw(RuntimeError("secret /private/path"))})
    valid = dict(strategy_id="s", dataset_id="d", window_id="w", cost_profile_id="c", idempotency_key="i")
    response = send(client, "/runs", "POST", json=dict(valid, tenant_id=system.b.tenant_id), headers={"Origin": ORIGIN, "X-CSRF-Token": system.ca})
    assert response.status_code == 400
    assert send(client, "/runs/" + str(uuid.uuid4())).get_json() == {"error": {"code": "not_found"}}
    assert send(client, "/runs", "POST", data="x" * 16385, content_type="application/json", headers={"Origin": ORIGIN}).status_code == 413
    assert send(client, "/runs", "POST", data="{}", content_type="text/plain", headers={"Origin": ORIGIN}).status_code == 400
    client.delete_cookie(SESSION, domain="demo.example")
    assert send(client, "/workspace").status_code == 401


def test_rate_limits_persist_and_cover_user_and_tenant(system):
    system.boundary.user_limit = 1
    assert send(app_client(system), "/workspace").status_code == 200
    assert send(app_client(system), "/workspace").status_code == 429
    assert send(app_client(system), "/workspace").status_code == 429
    system.boundary.user_limit, system.boundary.tenant_limit = 100, 3
    with transaction(system.connect) as conn:
        conn.execute("INSERT INTO memberships VALUES (?,?,'viewer',1)", (system.b.user_id, system.a.tenant_id))
        conn.execute("UPDATE memberships SET active=0 WHERE user_id=? AND workspace_id=?", (system.b.user_id, system.b.tenant_id))
    with pytest.raises(Denied) as error:
        system.boundary.call(system.sb, "workspace", lambda *_: "ok")
    assert error.value.status == 429


def test_provisioning_resume_drift_and_platform_scope(system):
    provisioner = Provisioner(system.control, system.platform, system.secrets, system.connections)
    provisioner.provision(system.a.tenant_id)
    assert len(system.platform.names) == 2
    with transaction(system.connect) as conn:
        conn.execute("UPDATE workspaces SET state='failed' WHERE id=?", (system.a.tenant_id,))
    provisioner.provision(system.a.tenant_id)
    endpoint = next(key for key in system.databases if system.a.tenant_id.replace("-", "") in key)
    with transaction(lambda: system.connections(endpoint, "workspaces/" + system.a.tenant_id + "/database")) as conn:
        conn.execute("UPDATE schema_migrations SET checksum='drift'")
    with transaction(system.connect) as conn:
        conn.execute("UPDATE workspaces SET state='failed' WHERE id=?", (system.a.tenant_id,))
    with pytest.raises(Denied):
        provisioner.provision(system.a.tenant_id)
    with transaction(system.connect) as conn:
        assert conn.execute("SELECT state,failure_code FROM workspaces WHERE id=?", (system.a.tenant_id,)).fetchone() == ("failed", "provisioning_failed")
    calls = []
    name = "ws-" + system.a.tenant_id.replace("-", "")
    def transport(method, path, body=None):
        calls.append((method, path, body))
        if method == "GET":
            return 200, {"database": {"Name": name, "Hostname": name + ".turso.io"}}
        if "/auth/tokens" in path:
            return 200, {"jwt": "synthetic"}
        return 409, {}
    platform = TursoPlatform("organization", "group", "fake-platform-token", transport=transport)
    assert platform.ensure_database(name).startswith("libsql://")
    assert platform.database_token(name) == "synthetic"
    assert "/databases/" + name + "/auth/tokens?expiration=1d&authorization=full-access" == calls[-1][1]
    assert calls[0][2] == {"name": name, "group": "group"}


def seed_resources(system, scope):
    run, result, artifact = [str(uuid.uuid4()) for _ in range(3)]
    session = system.sa if scope == system.a else system.sb
    def seed(conn, _):
        conn.execute("INSERT INTO runs VALUES (?)", (run,))
        conn.execute("INSERT INTO results VALUES (?,?)", (result, run))
        conn.execute("INSERT INTO result_artifacts VALUES (?,?)", (artifact, result))
    system.boundary.call(session, "status", seed)
    return run, result, artifact


@pytest.mark.parametrize("operation", ["status", "cancel", "result", "artifact"])
def test_http_cross_workspace_resource_denial(system, operation):
    own = seed_resources(system, system.a)
    other = seed_resources(system, system.b)
    called = []
    handler = lambda conn, scope, params: called.append(scope) or (b"synthetic" if operation == "artifact" else {"ok": True})
    client = app_client(system, {operation: handler})
    def resource(ids):
        run, result, artifact = ids
        return {"status": "/runs/" + run, "cancel": "/runs/" + run + "/cancel", "result": "/results/" + result, "artifact": "/results/" + result + "/artifacts/" + artifact}[operation]
    kwargs = {"json": {}, "headers": {"Origin": ORIGIN, "X-CSRF-Token": system.ca}} if operation == "cancel" else {}
    method = "POST" if operation == "cancel" else "GET"
    assert send(client, resource(other), method, **kwargs).status_code == 404
    assert not called
    assert send(client, resource(own), method, **kwargs).status_code == 200
    assert called == [system.a]
    if operation == "artifact":
        assert send(client, resource((own[0], other[1], own[2]))).status_code == 404


def test_http_errors_and_response_bounds_before_commit(system, caplog):
    run, _, _ = seed_resources(system, system.a)
    def faulty(conn, scope, params):
        conn.execute("INSERT INTO runs VALUES ('rolled-back')")
        raise RuntimeError("token-secret /private/path raw-body")
    client = app_client(system, {"status": faulty})
    response = send(client, "/runs/" + run)
    assert response.get_json() == {"error": {"code": "unavailable"}}
    assert "token-secret" not in caplog.text + response.get_data(as_text=True)
    def check(conn, _):
        assert conn.execute("SELECT id FROM runs WHERE id='rolled-back'").fetchone() is None
    system.boundary.call(system.sa, "status", check)
    client = app_client(system, {"status": lambda *_: "x" * (512 * 1024)})
    assert send(client, "/runs/" + run).status_code == 413


def test_http_cursor_rejected_before_handler_and_no_default_local_routes(system):
    client = app_client(system, {"list": lambda *_: pytest.fail("cross-tenant cursor used")})
    cursor = system.boundary.cursor(system.b, "position")
    assert send(client, "/research?cursor=" + cursor).status_code == 400
    assert send(client, "/research?limit=1&limit=2").status_code == 400
    assert send(client, "/research?limit=51").status_code == 400
    assert client.get("/api/demo/v1/strategies").status_code == 404


@pytest.mark.parametrize("stage", ["database", "secret", "migration", "ready_commit"])
def test_interrupted_provisioning_resumes_reserved_identity(system, stage):
    workspace = system.a.tenant_id
    with transaction(system.connect) as conn:
        conn.execute("UPDATE workspaces SET state='reserved',endpoint=NULL,secret_ref=NULL,schema_version=0 WHERE id=?", (workspace,))
    endpoint = next(key for key in system.databases if workspace.replace("-", "") in key)
    system.databases[endpoint].unlink()  # Fresh synthetic workspace only.
    provisioner = Provisioner(system.control, system.platform, system.secrets, system.connections)
    class Interrupt(BaseException):
        pass
    def interrupt(*args):
        raise Interrupt()
    if stage == "database":
        original = provisioner.platform.ensure_database
        def after_database(name):
            original(name)
            interrupt()
        provisioner.platform = SimpleNamespace(ensure_database=after_database)
    elif stage == "secret":
        original_put = system.secrets.put
        def after_secret(ref, token):
            original_put(ref, token)
            interrupt()
        provisioner.secrets = SimpleNamespace(put=after_secret)
    elif stage == "migration":
        provisioner.connections = interrupt
    else:
        original_connect = system.control.connect
        class Connection:
            def __init__(self):
                self.conn = original_connect()
            def execute(self, sql, params=()):
                if "SET state='ready'" in sql:
                    interrupt()
                return self.conn.execute(sql, params)
            def __getattr__(self, name):
                return getattr(self.conn, name)
        provisioner.control = Control(Connection)
    with pytest.raises(Interrupt):
        provisioner.provision(workspace)
    with transaction(system.connect) as conn:
        assert conn.execute("SELECT state FROM workspaces WHERE id=?", (workspace,)).fetchone() == ("initializing",)
    Provisioner(system.control, system.platform, system.secrets, system.connections).provision(workspace)
    assert system.control.reserve(system.a.user_id) == workspace
    assert len(system.platform.names) == 2
    assert system.boundary.call(system.sa, "workspace", lambda _, scope: scope.tenant_id) == workspace


@pytest.mark.parametrize("failure", ["missing", "cursor", "exception", "oversize"])
def test_failed_authorized_requests_consume_rate_budget(system, failure):
    run, _, _ = seed_resources(system, system.a)
    with transaction(system.connect) as conn:
        conn.execute("DELETE FROM rate_limits")
    system.boundary.user_limit = 1
    calls = []
    def handler(*_):
        calls.append(1)
        if failure == "exception":
            raise RuntimeError("synthetic")
        return "x" * (512 * 1024)
    client = app_client(system, {"status": handler, "list": handler})
    path = "/runs/" + (str(uuid.uuid4()) if failure == "missing" else run)
    if failure == "cursor":
        path = "/research?cursor=" + system.boundary.cursor(system.b, "position")
    assert send(client, path).status_code in {400, 404, 413, 503}
    assert send(client, path).status_code == 429
    assert send(client, path).status_code == 429
    assert len(calls) <= 1


@pytest.mark.parametrize("method,path", [("GET", "/workspace"), ("GET", "/runs/" + str(uuid.uuid4())), ("GET", "/research"), ("OPTIONS", "/runs")])
def test_every_http_method_enforces_request_body_limit(system, method, path):
    client = app_client(system)
    assert send(client, path, method, data=b"x" * 16385).status_code == 413
    assert send(client, path, method, data=b"x").status_code == 400
    # WSGI servers mark chunked/terminated input so Werkzeug bounds its stream.
    assert send(client, path, method, data=b"x" * 16385, environ_overrides={"CONTENT_LENGTH": "", "wsgi.input_terminated": True}).status_code == 413


@pytest.mark.parametrize("length", [None, ""])
def test_chunked_post_rejects_valid_json_prefix_with_oversized_tail(system, length):
    client = app_client(system)
    prefix = b"{}" + b" " * 16382
    response = send(client, "/auth/logout", "POST", data=prefix + b"hidden-tail", content_type="application/json", headers={"Origin": ORIGIN}, environ_overrides={"CONTENT_LENGTH": length, "wsgi.input_terminated": True})
    assert response.status_code == 413
    assert send(client, "/workspace").status_code == 200  # Logout never ran.
    assert send(client, "/auth/logout", "POST", data=prefix, content_type="application/json", headers={"Origin": ORIGIN}).status_code == 200


@pytest.mark.parametrize("claim,value", [("iat", True), ("iat", "1"), ("exp", "9999999999"), ("exp", True), ("nbf", "1"), ("nbf", False), ("exp", float("inf")), ("iat", float("nan"))])
def test_oidc_rejects_malformed_numeric_dates(claim, value):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signing_key = jwt.PyJWK(dict(json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())), kid="test", alg="RS256"))
    verifier = OIDCVerifier(ISSUER, "demo-client", ISSUER + "/jwks", jwks=SimpleNamespace(get_signing_key_from_jwt=lambda _: signing_key))
    claims = {"iss": ISSUER, "aud": "demo-client", "sub": "synthetic", "iat": time.time(), "exp": time.time() + 300, "nonce": "nonce"}
    valid = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test"})
    assert verifier.verify(valid, "nonce").subject == "synthetic"  # Fractional dates are valid.
    claims[claim] = value
    malformed = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test"})
    with pytest.raises(Denied):
        verifier.verify(malformed, "nonce")


def operation_states(system):
    with transaction(system.connect) as conn:
        return conn.execute("SELECT state,outcome FROM authorization_operations WHERE user_id=? ORDER BY created,id", (system.a.user_id,)).fetchall()


def test_control_connection_loss_cannot_acknowledge_early_revocation(system):
    captured = []
    def connect():
        conn = system.connect()
        captured.append(conn)
        return conn
    boundary = Boundary(Control(connect), system.connections, b"k" * 32)
    def handler(conn, _):
        captured[-1].close()  # Simulates loss of the old admission connection.
        with pytest.raises(Denied) as error:
            system.control.revoke(system.a.user_id, system.a.tenant_id)
        assert error.value.code == "revocation_pending"
        conn.execute("INSERT INTO runs VALUES ('admitted-before-pending')")
        return "ok"
    assert boundary.call(system.sa, "status", handler) == "ok"
    assert operation_states(system) == [("completed", "committed")]
    system.control.revoke(system.a.user_id, system.a.tenant_id)  # Success now, never before commit.
    with pytest.raises(Denied):
        boundary.call(system.sa, "status", lambda *_: pytest.fail("late operation"))


@pytest.mark.parametrize("fault", ["commit_before_failure", "commit_without_server_commit", "rollback", "final_control", "crash"])
def test_uncertain_operations_remain_durable_revocation_fences(system, fault):
    class FaultyConnection:
        def __init__(self, conn):
            self.conn = conn
        def __getattr__(self, name):
            return getattr(self.conn, name)
        def commit(self):
            if fault == "commit_before_failure":
                self.conn.commit()
            if fault in {"commit_before_failure", "commit_without_server_commit"}:
                raise RuntimeError("synthetic lost commit response")
            self.conn.commit()
        def rollback(self):
            if fault == "rollback":
                raise RuntimeError("synthetic lost rollback response")
            self.conn.rollback()
    count = [0]
    def control_connect():
        count[0] += 1
        if fault == "final_control" and count[0] == 2:
            raise RuntimeError("synthetic control loss")
        return system.connect()
    boundary = Boundary(Control(control_connect), lambda *args: FaultyConnection(system.connections(*args)), b"k" * 32)
    class Crash(BaseException):
        pass
    def handler(conn, _):
        conn.execute("INSERT INTO runs VALUES ('admitted')")
        if fault == "crash":
            raise Crash()
        if fault == "rollback":
            raise RuntimeError("synthetic handler error")
    with pytest.raises((RuntimeError, Crash)):
        boundary.call(system.sa, "status", handler)
    states = operation_states(system)
    assert len(states) == 1 and states[0][0] in {"active", "uncertain"}
    assert states[0][1] is None
    for _ in range(2):
        with pytest.raises(Denied) as error:
            system.control.revoke(system.a.user_id, system.a.tenant_id)
        assert error.value.code == "revocation_pending"
    with pytest.raises(Denied):
        system.boundary.call(system.sa, "status", lambda *_: pytest.fail("revoked admission"))


def test_confirmed_rollback_completes_admission(system):
    def handler(conn, _):
        conn.execute("INSERT INTO runs VALUES ('rolled-back')")
        raise ValueError("synthetic handler error")
    with pytest.raises(ValueError):
        system.boundary.call(system.sa, "status", handler)
    assert operation_states(system) == [("completed", "rolled_back")]
    system.control.revoke(system.a.user_id, system.a.tenant_id)


def test_control_schema_upgrade_preserves_v1_checksum(tmp_path):
    connect = lambda: sqlite3.connect(tmp_path / "legacy-control.db", isolation_level=None)
    with transaction(connect) as conn:
        for statement in CONTROL:
            conn.execute(statement)
        conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY,checksum TEXT NOT NULL)")
        conn.execute("INSERT INTO schema_migrations VALUES (1,?)", (digest("\n".join(CONTROL)),))
        conn.execute("INSERT INTO users VALUES ('saved','https://synthetic.example','subject')")
    migrate(connect, CONTROL)
    migrate(connect, CONTROL)
    with transaction(connect) as conn:
        rows = conn.execute("SELECT version,checksum FROM schema_migrations ORDER BY version").fetchall()
        assert [row[0] for row in rows] == [1, 2]
        assert rows[0][1] == digest("\n".join(CONTROL))
        assert conn.execute("SELECT id FROM users").fetchall() == [("saved",)]


@pytest.mark.parametrize("server_committed", [False, True])
def test_lost_control_admission_commit_never_starts_workspace_work(system, server_committed):
    class Connection:
        def __init__(self):
            self.conn = system.connect()
        def __getattr__(self, name):
            return getattr(self.conn, name)
        def commit(self):
            if server_committed:
                self.conn.commit()
            raise RuntimeError("synthetic admission commit response lost")
    boundary = Boundary(Control(Connection), lambda *_: pytest.fail("workspace opened after unknown admission"), b"k" * 32)
    with pytest.raises(RuntimeError):
        boundary.call(system.sa, "status", lambda *_: pytest.fail("handler after unknown admission"))
    if server_committed:
        assert operation_states(system) == [("active", None)]
        with pytest.raises(Denied) as error:
            system.control.revoke(system.a.user_id, system.a.tenant_id)
        assert error.value.code == "revocation_pending"
    else:
        assert operation_states(system) == []
        system.control.revoke(system.a.user_id, system.a.tenant_id)


def test_control_v2_migration_drift_fails_closed(system):
    with transaction(system.connect) as conn:
        conn.execute("UPDATE schema_migrations SET checksum='drift' WHERE version=2")
    with pytest.raises(Denied) as error:
        migrate(system.connect, CONTROL)
    assert error.value.code == "schema_mismatch"

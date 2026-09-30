"""Separate hosted Flask factory; C3/C4 inject bounded persistence handlers.

No default handler reads local files, invokes the engine, or sends broker orders.
"""
import hmac
import json
from urllib.parse import urlsplit

from flask import Flask, jsonify, make_response, request
from werkzeug.exceptions import HTTPException

from .store import Denied, canonical_id


SESSION = "__Host-demo-session"
LOGIN = "__Host-demo-login"
ROUTES = (
    ("/runs", "POST", "submit"),
    ("/runs/<run_id>", "GET", "status"),
    ("/runs/<run_id>/cancel", "POST", "cancel"),
    ("/results/<result_id>", "GET", "result"),
    ("/results/<result_id>/artifacts/<artifact_id>", "GET", "artifact"),
    ("/research", "GET", "list"),
)
SUBMIT_FIELDS = {"strategy_id", "dataset_id", "window_id", "cost_profile_id", "idempotency_key"}


def create_hosted_app(control, verifier, boundary, *, origin, handlers=None):
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise ValueError("Canonical HTTPS application origin required")
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=16384)
    handlers = dict(handlers or {})

    def cookie(response, name, value, max_age):
        response.set_cookie(name, value, max_age=max_age, secure=True, httponly=True, samesite="Strict", path="/")

    @app.before_request
    def guard():
        if request.headers.get("Origin") not in {None, origin}:
            raise Denied("origin_denied", 403)
        if request.headers.get("Sec-Fetch-Site") not in {None, "same-origin", "none"}:
            raise Denied("origin_denied", 403)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.headers.get("Origin") != origin:
                raise Denied("origin_denied", 403)
            if request.mimetype != "application/json":
                raise Denied("invalid_request", 400)
        if request.headers.get("Authorization") or any(name in request.args for name in ("tenant", "tenant_id", "workspace", "workspace_id", "database_url", "cache_key")):
            raise Denied("invalid_request", 400)

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        # Deliberately no cross-origin credentials or wildcard CORS headers.
        return response

    @app.errorhandler(Exception)
    def error(exc):
        if isinstance(exc, Denied):
            code, status = exc.code, exc.status
        elif isinstance(exc, HTTPException):
            status = exc.code
            code = {400: "invalid_request", 404: "not_found", 405: "method_not_allowed", 413: "too_large"}.get(status, "invalid_request")
        else:
            code, status = "unavailable", 503
        return jsonify(error={"code": code}), status

    def body(fields):
        value = request.get_json()
        if not isinstance(value, dict) or set(value) != fields:
            raise Denied("invalid_request", 400)
        if any(not isinstance(item, str) or not 1 <= len(item) <= 16384 for item in value.values()):
            raise Denied("invalid_request", 400)
        return value

    @app.post("/api/hosted/v1/auth/challenge")
    def challenge():
        body(set())
        state, nonce = control.challenge()
        response = jsonify(data={"state": state, "nonce": nonce})
        cookie(response, LOGIN, state, 300)
        return response

    @app.post("/api/hosted/v1/auth/login")
    def login():
        value = body({"state", "id_token"})
        expected = request.cookies.get(LOGIN, "")
        if not expected or not hmac.compare_digest(value["state"], expected):
            raise Denied()
        session, csrf, user = control.login(value["state"], value["id_token"], verifier)
        workspace = control.reserve(user)
        response = jsonify(data={"user_id": user, "workspace_id": workspace, "csrf_token": csrf})
        cookie(response, SESSION, session, 3600)
        cookie(response, LOGIN, "", 0)
        return response

    @app.post("/api/hosted/v1/auth/logout")
    def logout():
        body(set())
        # Logout only destroys the presented high-entropy session; exact Origin
        # is required even when its workspace is not yet ready/revoked.
        control.logout(request.cookies.get(SESSION, ""))
        response = jsonify(data={"logged_out": True})
        cookie(response, SESSION, "", 0)
        return response

    def materialize(operation, params):
        def invoke(conn, scope):
            if operation in {"status", "cancel"}:
                if conn.execute("SELECT id FROM runs WHERE id=?", (params["run_id"],)).fetchone() is None:
                    raise Denied("not_found", 404)
            elif operation == "result":
                if conn.execute("SELECT id FROM results WHERE id=?", (params["result_id"],)).fetchone() is None:
                    raise Denied("not_found", 404)
            elif operation == "artifact":
                if conn.execute("SELECT a.id FROM result_artifacts a JOIN results r ON r.id=a.result_id WHERE a.id=? AND r.id=?", (params["artifact_id"], params["result_id"])).fetchone() is None:
                    raise Denied("not_found", 404)
            if operation == "workspace":
                data = {"user_id": scope.user_id, "workspace_id": scope.tenant_id, "role": scope.role}
            else:
                handler = handlers.get(operation)
                if handler is None:
                    raise Denied("unavailable", 503)
                if operation == "list" and params.get("cursor"):
                    params["position"] = boundary.read_cursor(scope, params.pop("cursor"))
                data = handler(conn, scope, params)
            if operation == "artifact":
                if not isinstance(data, bytes) or len(data) > 1024 * 1024:
                    raise Denied("too_large", 413)
                return data
            encoded = json.dumps({"schema_version": 1, "data": data, "warnings": []}, allow_nan=False).encode()
            if len(encoded) > 512 * 1024:
                raise Denied("too_large", 413)
            return encoded
        data = boundary.call(request.cookies.get(SESSION), operation, invoke, csrf=request.headers.get("X-CSRF-Token"))
        response = make_response(data)
        response.mimetype = "application/octet-stream" if operation == "artifact" else "application/json"
        return response

    @app.get("/api/hosted/v1/workspace")
    def workspace():
        if request.args:
            raise Denied("invalid_request", 400)
        return materialize("workspace", {})

    def endpoint(operation):
        def view(**params):
            for value in params.values():
                canonical_id(value)
            if operation == "submit":
                params.update(body(SUBMIT_FIELDS))
            elif operation == "cancel":
                body(set())
            if operation == "list":
                if set(request.args) - {"cursor", "limit"} or any(len(request.args.getlist(key)) != 1 for key in request.args):
                    raise Denied("invalid_request", 400)
                try:
                    page_limit = int(request.args.get("limit", "20"))
                    if not 1 <= page_limit <= 50:
                        raise ValueError()
                except ValueError:
                    raise Denied("invalid_request", 400) from None
                params.update(limit=page_limit, cursor=request.args.get("cursor"))
            elif request.args:
                raise Denied("invalid_request", 400)
            return materialize(operation, params)
        return view

    for path, method, operation in ROUTES:
        app.add_url_rule("/api/hosted/v1" + path, operation, endpoint(operation), methods=[method])
    return app

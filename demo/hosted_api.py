"""Hosted-only HTTP authorization boundary, requiring explicit durable adapters.

No local journal, replay, broker, or LLM imports. This is not a deployment entrypoint.
"""
from urllib.parse import urlsplit
import uuid

from flask import Flask, Response, jsonify, request
from werkzeug.exceptions import HTTPException

from .hosted_identity import BoundaryDenied


READS = {
    "strategies": "strategies", "datasets": "datasets", "cost-profiles": "cost_profiles",
    "replay-catalog": "replay_catalog", "research": "research", "runs": "runs",
}


def create_hosted_app(*, identity, limiter, service, origin):
    """service.handle(conn, scope, operation, ids, query, body) is a C3+ adapter.

    It MUST use the supplied tenant transaction and return only public A1 data;
    unknown and wrong-tenant objects/cursors must raise BoundaryDenied('not_found',404).
    Artifact returns are (bytes, allowlisted MIME type). No client-selected cache key.
    """
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("A canonical HTTPS origin is required")
    if any(adapter is None for adapter in (identity, limiter, service)):
        raise ValueError("Hosted adapters are required")
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 4096

    @app.errorhandler(Exception)
    def failure(exc):
        # Never stringify, log, or return an exception supplied by an adapter.
        if isinstance(exc, BoundaryDenied):
            codes = {"unauthenticated", "forbidden", "csrf_rejected", "tenant_unavailable",
                     "rate_limited", "not_found", "invalid_request", "content_too_large"}
            code, status = (exc.code, exc.status) if exc.code in codes else ("unavailable", 503)
        elif isinstance(exc, HTTPException):
            status = exc.code
            code = {404: "not_found", 405: "method_not_allowed", 413: "content_too_large"}.get(status, "invalid_request")
        else:
            code, status = "unavailable", 503
        response = jsonify(error={"code": code, "message": code.replace("_", " ")})
        response.status_code = status
        return response

    @app.after_request
    def private_response(response):
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Vary"] = "Cookie, Origin"
        if response.status_code == 429:
            response.headers["Retry-After"] = "60"
        return response

    def dispatch(operation, ids=()):
        mutation = request.method == "POST"
        if request.host != parsed.netloc:
            raise BoundaryDenied("forbidden", 403)
        if request.headers.get("Origin") not in (None, origin):
            raise BoundaryDenied("csrf_rejected", 403)
        if mutation and (request.headers.get("Origin") != origin or not request.is_json):
            raise BoundaryDenied("csrf_rejected", 403)
        csrf = request.headers.get("X-CSRF-Token", "") if mutation else None
        scope = identity.authenticate(request.cookies.get("__Host-demo-session"), csrf)
        limiter.check(scope)
        if mutation:
            scope.require_write()
        # Reject client ownership overrides rather than ignoring them.
        if set(request.args) - {"cursor", "limit"}:
            raise BoundaryDenied("invalid_request", 400)
        if any(len(request.args.getlist(key)) != 1 for key in request.args):
            raise BoundaryDenied("invalid_request", 400)
        if any(key in request.headers for key in ("X-Tenant-ID", "X-User-ID", "X-Owner-ID", "X-Cache-Key")):
            raise BoundaryDenied("invalid_request", 400)
        for value in (*ids, *request.args.getlist("cursor")):
            try:
                if str(uuid.UUID(value)) != value:
                    raise ValueError()
            except ValueError:
                raise BoundaryDenied("not_found", 404) from None
        body = request.get_json(silent=True) if mutation else None
        if mutation:
            fields = {"strategy_id", "dataset_id", "window_id", "cost_profile_id", "idempotency_key"} if operation == "submit" else set()
            if not isinstance(body, dict) or set(body) != fields:
                raise BoundaryDenied("invalid_request", 400)
        with identity.transaction(scope) as conn:
            identity.authorize_resources(conn, scope, operation, ids, dict(request.args))
            payload = service.handle(conn, scope, operation, ids, dict(request.args), body)
        if operation.endswith("artifact"):
            content, mime = payload
            if not isinstance(content, bytes) or len(content) > 1024 * 1024:
                raise BoundaryDenied("content_too_large", 413)
            if mime not in {"application/json", "text/plain", "text/csv"}:
                raise BoundaryDenied("not_found", 404)
            return Response(content, mimetype=mime)
        response = jsonify(payload)
        if len(response.get_data()) > 512 * 1024:
            raise BoundaryDenied("content_too_large", 413)
        if operation == "submit":
            response.status_code = 202
        return response

    for path, operation in READS.items():
        app.add_url_rule("/api/demo/v1/" + path, operation,
                         lambda operation=operation: dispatch(operation), methods=["GET"],
                         provide_automatic_options=False)
    app.add_url_rule("/api/demo/v1/runs", "submit", lambda: dispatch("submit"), methods=["POST"],
                     provide_automatic_options=False)
    for collection, singular in (("runs", "run"), ("results", "result")):
        app.add_url_rule("/api/demo/v1/" + collection + "/<resource_id>", singular,
                         lambda resource_id, singular=singular: dispatch(singular, (resource_id,)),
                         methods=["GET"], provide_automatic_options=False)
        app.add_url_rule("/api/demo/v1/" + collection + "/<resource_id>/artifacts/<artifact_id>", singular + "_artifact",
                         lambda resource_id, artifact_id, singular=singular: dispatch(singular + "_artifact", (resource_id, artifact_id)),
                         methods=["GET"], provide_automatic_options=False)
    app.add_url_rule("/api/demo/v1/runs/<resource_id>/cancel", "cancel",
                     lambda resource_id: dispatch("cancel", (resource_id,)), methods=["POST"],
                     provide_automatic_options=False)
    return app

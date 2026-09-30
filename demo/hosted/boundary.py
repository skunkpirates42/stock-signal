"""Authorization, rate limits and scoped cursor/cache identities."""
import base64
import hmac
import json

from .store import Denied, Scope, check_binding, digest, limit, now, transaction


OPERATIONS = {"workspace", "submit", "status", "cancel", "result", "artifact", "list"}


class Boundary:
    def __init__(self, control, connections, cursor_key, *, user_limit=60, tenant_limit=120):
        if not isinstance(cursor_key, bytes) or len(cursor_key) < 32:
            raise ValueError("Cursor key must contain at least 32 bytes")
        if any(type(value) is not int or value < 1 for value in (user_limit, tenant_limit)):
            raise ValueError("Positive rate limits required")
        self.control, self.connections, self.cursor_key = control, connections, cursor_key
        self.user_limit, self.tenant_limit = user_limit, tenant_limit

    def call(self, session, operation, handler, *, csrf=None):
        if operation not in OPERATIONS:
            raise Denied("forbidden", 403)
        if not isinstance(session, str) or not 1 <= len(session) <= 128:
            raise Denied()
        denied = None
        result = None
        # Hold the authoritative membership lock until the bounded workspace
        # transaction commits and the response is materialized. Revocation uses
        # the same lock. No streaming, remote uploads, replay, or nested control
        # operations are permitted in handlers. Separate processes for libSQL.
        with transaction(self.control.connect) as control:
            row = control.execute("SELECT user_id,csrf_hash FROM sessions WHERE id_hash=? AND expires>?", (digest(session), now(control))).fetchone()
            if row is None:
                raise Denied()
            if operation in {"submit", "cancel"} and (not isinstance(csrf, str) or not hmac.compare_digest(row[1], digest(csrf))):
                raise Denied("csrf", 403)
            memberships = control.execute(
                "SELECT w.id,m.role,w.endpoint,w.secret_ref,w.state,w.schema_version FROM memberships m JOIN workspaces w ON w.id=m.workspace_id WHERE m.user_id=? AND m.active=1", (row[0],)).fetchall()
            if len(memberships) != 1:
                raise Denied("forbidden", 403)
            workspace, role, endpoint, secret_ref, state, version = memberships[0]
            if state != "ready" or version != 1 or not endpoint or not secret_ref:
                raise Denied("workspace_unavailable", 503)
            scope = Scope(row[0], workspace, role)
            # Persist counters even when denying a request.
            user_ok = limit(control, "user:" + scope.user_id, self.user_limit)
            tenant_ok = limit(control, "tenant:" + scope.tenant_id, self.tenant_limit)
            if not user_ok or not tenant_ok:
                denied = Denied("rate_limited", 429)
            elif operation in {"submit", "cancel"} and role == "viewer":
                denied = Denied("forbidden", 403)
            else:
                try:
                    with transaction(lambda: self.connections(endpoint, secret_ref)) as conn:
                        check_binding(conn, workspace)
                        result = handler(conn, scope)
                except Exception as exc:
                    # The workspace rolls back, but quota consumption must
                    # survive failing/expensive handlers and malformed cursors.
                    denied = exc
        if denied:
            raise denied
        return result

    def cache_key(self, scope, operation, value):
        if operation not in OPERATIONS:
            raise Denied("invalid_request", 400)
        return digest(json.dumps([scope.user_id, scope.tenant_id, operation, value], sort_keys=True, allow_nan=False))

    def cursor(self, scope, position):
        payload = json.dumps([scope.user_id, scope.tenant_id, "list", position], separators=(",", ":")).encode()
        signature = hmac.digest(self.cursor_key, payload, "sha256")
        return base64.urlsafe_b64encode(signature + payload).decode()

    def read_cursor(self, scope, value):
        try:
            if not isinstance(value, str) or len(value) > 2048:
                raise ValueError()
            raw = base64.b64decode(value, altchars=b"-_", validate=True)
            if not hmac.compare_digest(raw[:32], hmac.digest(self.cursor_key, raw[32:], "sha256")):
                raise ValueError()
            user, tenant, purpose, position = json.loads(raw[32:])
            if (user, tenant, purpose) != (scope.user_id, scope.tenant_id, "list"):
                raise ValueError()
            return position
        except Exception:
            raise Denied("invalid_cursor", 400) from None

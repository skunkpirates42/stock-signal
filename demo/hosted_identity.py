"""Opt-in hosted identity boundary. Never imported by the local dashboard.

The deployment supplies PostgreSQL connections; provider login redirects/code exchange
are deliberately outside this module. Only the trusted callback calls finish_login.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import secrets
import uuid
from urllib.parse import urlsplit

import jwt


class BoundaryDenied(Exception):
    """Only fixed codes cross the public boundary."""
    def __init__(self, code="unauthenticated", status=401):
        self.code, self.status = code, status
        super().__init__(code)


@dataclass(frozen=True)
class Scope:
    user_id: str
    tenant_id: str
    role: str

    def __post_init__(self):
        for value in (self.user_id, self.tenant_id):
            if str(uuid.UUID(value)) != value:
                raise ValueError("Scope IDs must be canonical UUIDs")
        if self.role not in {"owner", "operator", "viewer"}:
            raise ValueError("Invalid membership role")

    def require_write(self):
        if self.role not in {"owner", "operator"}:
            raise BoundaryDenied("forbidden", 403)

    def cache_key(self, namespace, resource_id):
        # Tuple components cannot collide through delimiter injection.
        return (self.tenant_id, self.user_id, self.role, namespace, resource_id)


class OIDCVerifier:
    """RS256 only; keys come exclusively from a configured HTTPS JWKS endpoint."""
    def __init__(self, issuer, audience, jwks_uri):
        for url in (issuer, jwks_uri):
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.fragment:
                raise ValueError("OIDC URLs must be configured HTTPS URLs")
        if not isinstance(audience, str) or not audience:
            raise ValueError("OIDC audience is required")
        self.issuer, self.audience = issuer, audience
        # No unbounded per-key cache: removed keys expire with the JWKS set.
        self.keys = jwt.PyJWKClient(jwks_uri, cache_keys=False, lifespan=300,
                                    timeout=5, cooldown_duration=30)

    def verify(self, token, expected_nonce):
        try:
            if not isinstance(token, str) or len(token) > 16384:
                raise ValueError()
            if not isinstance(expected_nonce, str) or not expected_nonce:
                raise ValueError()
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise ValueError()
            key = self.keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(token, key.key, algorithms=["RS256"],
                                issuer=self.issuer, audience=self.audience,
                                options={"require": ["iss", "aud", "exp", "iat", "sub", "nonce"]})
            if not isinstance(claims["sub"], str) or not claims["sub"] or len(claims["sub"]) > 255:
                raise ValueError()
            if not isinstance(claims["nonce"], str) or not secrets.compare_digest(claims["nonce"], expected_nonce):
                raise ValueError()
            if any(type(claims[key]) is not int for key in ("iat", "exp")):
                raise ValueError()
            audiences = claims["aud"]
            if (isinstance(audiences, list) and len(audiences) > 1) or "azp" in claims:
                if claims.get("azp") != self.audience:
                    raise ValueError()
            return claims
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            raise BoundaryDenied() from None


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PostgresIdentity:
    """Connection factory must use a non-owner, non-superuser, NOBYPASSRLS role.

    Membership provisioning is a separate administrative operation. A new login
    creates an identity, never an automatic tenant membership.
    """
    def __init__(self, connect, *, data_connect):
        self.connect = connect
        self.data_connect = data_connect

    def begin_login(self):
        challenge, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.connect() as conn:
            conn.execute("INSERT INTO hosted_login_challenges (id_hash, nonce, expires_at) "
                         "VALUES (%s, %s, clock_timestamp() + interval '5 minutes')",
                         (_digest(challenge), nonce))
        return challenge, nonce

    def finish_login(self, verifier, challenge, token):
        if not isinstance(challenge, str) or not 20 <= len(challenge) <= 128:
            raise BoundaryDenied()
        # Consume even failed attempts; a challenge cannot be replayed concurrently.
        with self.connect() as conn:
            row = conn.execute("DELETE FROM hosted_login_challenges WHERE id_hash=%s "
                               "AND expires_at > clock_timestamp() RETURNING nonce",
                               (_digest(challenge),)).fetchone()
        if row is None:
            raise BoundaryDenied()
        claims = verifier.verify(token, row[0])
        session, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.connect() as conn:
            user = conn.execute("INSERT INTO hosted_users (id, issuer, subject) VALUES (%s,%s,%s) "
                                "ON CONFLICT (issuer, subject) DO UPDATE SET subject=EXCLUDED.subject "
                                "RETURNING id", (str(uuid.uuid4()), claims["iss"], claims["sub"])).fetchone()
            conn.execute("INSERT INTO hosted_sessions (id_hash,user_id,csrf_hash,expires_at) "
                         "VALUES (%s,%s,%s,LEAST(to_timestamp(%s),clock_timestamp()+interval '1 hour'))",
                         (_digest(session), user[0], _digest(csrf), claims["exp"]))
        return session, csrf

    def authenticate(self, session, csrf=None):
        if not isinstance(session, str) or not 20 <= len(session) <= 128:
            raise BoundaryDenied()
        with self.connect() as conn:
            row = conn.execute("SELECT user_id,csrf_hash FROM hosted_sessions WHERE id_hash=%s "
                               "AND expires_at > clock_timestamp()", (_digest(session),)).fetchone()
            if row is None:
                raise BoundaryDenied()
            if csrf is not None and (not isinstance(csrf, str) or
                                      not secrets.compare_digest(row[1], _digest(csrf))):
                raise BoundaryDenied("csrf_rejected", 403)
            conn.execute("SELECT set_config('app.user_id', %s, true)", (str(row[0]),))
            memberships = conn.execute("SELECT tenant_id,role FROM hosted_memberships WHERE user_id=%s",
                                       (row[0],)).fetchall()
        if len(memberships) != 1:
            raise BoundaryDenied("tenant_unavailable", 403)
        return Scope(str(row[0]), str(memberships[0][0]), memberships[0][1])

    def revoke(self, session):
        with self.connect() as conn:
            conn.execute("DELETE FROM hosted_sessions WHERE id_hash=%s", (_digest(session),))

    def authorize_resources(self, conn, scope, operation, ids, query):
        checks = []
        if ids:
            kind = "run" if operation in {"run", "run_artifact", "cancel"} else "result"
            checks.append((ids[0], kind, None))
            if len(ids) == 2:
                checks.append((ids[1], "artifact", ids[0]))
        if "cursor" in query:
            if operation not in {"runs", "research"}:
                raise BoundaryDenied("invalid_request", 400)
            checks.append((query["cursor"], "run" if operation == "runs" else "result", None))
        for resource_id, kind, parent in checks:
            row = conn.execute("SELECT parent_id FROM hosted_resources "
                               "WHERE tenant_id=%s AND id=%s AND kind=%s",
                               (scope.tenant_id, resource_id, kind)).fetchone()
            if row is None or (parent is not None and str(row[0]) != parent):
                raise BoundaryDenied("not_found", 404)

    @contextmanager
    def transaction(self, scope):
        with self.data_connect() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (scope.user_id,))
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (scope.tenant_id,))
            # Recheck membership inside the operation transaction, including revocation.
            rows = conn.execute("SELECT tenant_id,role FROM hosted_memberships WHERE user_id=%s FOR SHARE",
                                (scope.user_id,)).fetchall()
            if len(rows) != 1 or (str(rows[0][0]), rows[0][1]) != (scope.tenant_id, scope.role):
                raise BoundaryDenied("tenant_unavailable", 403)
            yield conn


class PostgresRateLimit:
    """Shared fixed-minute counters; both dimensions update atomically."""
    def __init__(self, connect, *, user_limit=60, tenant_limit=300):
        if user_limit < 1 or tenant_limit < 1:
            raise ValueError("Positive rate limits are required")
        self.connect, self.limits = connect, (user_limit, tenant_limit)

    def check(self, scope):
        allowed = True
        with self.connect() as conn:
            for kind, identity, maximum in (("user", scope.user_id, self.limits[0]),
                                             ("tenant", scope.tenant_id, self.limits[1])):
                row = conn.execute("INSERT INTO hosted_rate_buckets (kind,identity,bucket,count) "
                                   "VALUES (%s,%s,date_trunc('minute',statement_timestamp()),1) "
                                   "ON CONFLICT (kind,identity,bucket) DO UPDATE "
                                   "SET count=hosted_rate_buckets.count+1 RETURNING count",
                                   (kind, identity)).fetchone()
                allowed = allowed and row[0] <= maximum
        if not allowed:
            raise BoundaryDenied("rate_limited", 429)

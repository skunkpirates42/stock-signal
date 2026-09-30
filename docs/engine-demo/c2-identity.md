# C2 identity and workspace boundary (#45)

The opt-in `demo.hosted` package is separate from `dashboard.app` and all local
B1–B5 routes. It does not start a server, enable hosted writes, provision a real
database, or invoke a replay. No broker dependency is imported.

## Identity and request contract

Install optional dependencies from `demo/hosted/requirements.txt`. Configure an
exact HTTPS issuer, client audience, JWKS URL, and application origin; no discovery
URL or key location comes from the request. `OIDCVerifier` accepts RS256 ID tokens
only at login, requiring issuer, subject, audience, expiry, issued-at and nonce.
It verifies authorized-party claims for multiple audiences. PyJWT refreshes a
missing key once; key-set cache lifetime is 60 seconds with no permanent per-key
cache. Provider-specific algorithms and rotation policies require new configuration
and verification before deployment.

Same-origin JSON `POST /api/hosted/v1/auth/challenge` reserves a five-minute nonce
and state. The client uses these with its configured OIDC provider and sends
`{state,id_token}` to `/auth/login`. A Secure, HttpOnly, SameSite=Strict, host-only
login cookie must match the challenge. The challenge is consumed before token
verification, including failures. Verified `(issuer,subject)` maps to one stable
internal UUID. A one-hour opaque session is stored hashed in the control database;
the response supplies a CSRF token and reserves the personal workspace. Login never
receives a provisioning credential and never marks an uninitialized database ready.

Provider selection, redirect/code exchange and PKCE integration are deployment
work, not simulated by this package. The only resource authentication transport is
the host-only opaque session cookie; bearer headers are rejected. ID tokens are
never used as API bearer credentials. Logout deletes the presented session and
requires exact Origin even for a revoked or unprovisioned workspace.

All resource operations resolve exactly one active membership on every call. Zero
or multiple memberships deny access. The selected workspace must be ready at the
supported schema version, with endpoint and secret reference in the registry.
Owner/operator can submit and cancel; viewer can read. Resource IDs are canonical
UUIDs, and runs/results/artifacts are looked up inside the selected workspace.
Artifact lookup also checks its result parent. Request bodies have exact field
allowlists. No tenant, URL, credential, cache key or object path is accepted from
the caller. List cursors are HMAC-bound to user, workspace and purpose; cache keys
include user and workspace. Responses use `no-store`.

Commands require exact Origin, JSON and session-bound `X-CSRF-Token`. Cross-origin
requests/preflights and cross-site fetch metadata are denied; the API emits no CORS
allow headers. Limits are 16 KiB request body, 512 KiB JSON response, 1 MiB artifact
response, and 50 rows/page. A global 60/minute challenge budget bounds anonymous
login work. Durable fixed-minute limits default to 60/user and 120/workspace;
deployment may set explicit positive limits. Errors contain stable codes only,
without exception text, headers, tokens, paths, request bodies or tracebacks.

## Registry and provisioning

`migrate(connect, CONTROL)` installs the shared users, memberships, workspace
registry, challenges, sessions and rate-limit tables. The provisioning service
reserves one UUID/name per personal user and records `initializing` durably before
external work. It uses a deterministic `ws-<uuid hex>` Turso database name, resolves
create conflicts by retrieving the exact name, and mints a one-day database-scoped
token. Only the administrative process holds the platform token.

Inject a deployment secret store implementing `put(ref, token)` as an atomic
replacement and `get(ref)` for server-side connections. The registry stores only
the reference. Retry remints a token, safely replacing an expired initialization
credential. Runtime token rotation is a separate administrative duty required
before deployment; a ready workspace is not automatically reprovisioned by login.
The secret store must enforce administrative-write/runtime-read separation.

Version-1 workspace migrations and fixed UUID binding are atomic and checksummed.
Drift or a different binding fails closed. Foreign keys establish run → result →
artifact parents. The minimal C2 parent tables deliberately contain only identity
columns; C3 must add lifecycle fields via a new checksummed migration, preserving
the version-1 statements/checksum and updating supported-version checks together.
Readiness is recorded only after migration and binding verification. Interruptions
resume by the same reserved name; failures persist a bounded failure code. Nothing
is deleted on rollback. Fleet migration/rollout is C7.

`remote_connections` uses direct authoritative `libsql==0.1.11` connections with
explicit transaction management and database-scoped secrets. No embedded replicas
or offline sync are allowed. Use separate processes for concurrent libSQL work;
the proof's threaded driver failure remains applicable. C6 must verify actual
database-scoped cross-database denial and exact deployed runtime permissions.

## Revocation racing an operation

There is no cross-database atomic transaction and no PostgreSQL advisory lock.
Every bounded request obtains `BEGIN IMMEDIATE` on the authoritative control
database, checks session/current membership, then obtains the selected workspace
transaction, verifies UUID/checksum, performs the handler, materializes its bounded
response and commits the workspace before releasing the control transaction.
Administrative membership changes and session logout use the same control write
serialization. No caller can retain an authorized connection after the call.

The ordering contract is: if revocation commits first, the operation is denied;
if authorization obtains the control lock first, that operation may finish and
revocation waits. After successful revocation, no later operation can use that
membership. Bytes already materialized can arrive over the network after revocation;
this does not retroactively retract previously authorized data. C3 workers require
their own explicit cancellation/dispatch authorization policy, not a cached scope.

Control failure after a workspace commit can leave a committed operation with an
unavailable response. No automatic retry is attempted. C3 must resolve uncertain
outcomes using stable idempotency keys. A connection loss/unknown remote transaction
outcome must not count as a successful revocation acknowledgment. Requests must be
bounded by deployment timeouts; streaming, replay, object downloads/uploads and
nested control transactions are prohibited inside handlers. Artifact handlers must
return bounded bytes from private C4 storage under an authorized parent row.

This conservative implementation serializes operations across the entire control
database. It is a correctness baseline, not a scalability claim. Staging must test
remote lock/connection-loss behavior, timeouts and throughput before enabling
hosted writes. An optimized distributed fencing protocol requires a new review.

## Integration and evidence

`create_hosted_app` mounts only `/api/hosted/v1`. C3/C4 supply trusted handlers for
submit/status/cancel/result/artifact/list accepting `(connection, scope, params)`.
The boundary owns and closes the connection. Missing handlers return unavailable;
they never fall back to local SQLite/filesystem data. Handlers must return bounded
JSON-serializable data (artifact: bytes) and cannot return connections or generators.
The current factory has no production bootstrap or default replay/object handlers.

Offline `tests/test_hosted_identity.py` uses synthetic RSA keys, fake JWKS rotation,
two separate SQLite workspaces, fake secret/platform providers and spawned process
revocation races. It covers invalid identities, nonce reuse, stable user mapping,
roles, ambiguous/expired/revoked sessions, registry binding/checksum faults, scoped
resource/cursor/cache authorization, CSRF/origin/CORS, persisted quotas, parent
foreign keys, bounded responses, rollback and safe errors. Existing local route
tests remain the regression evidence for B1–B5.

This is implementation evidence, not hosted launch clearance. Production provider
integration, remote revocation/fault evidence, token/secret-store permissions, C3–C7,
independent Astra review and human security review remain launch prerequisites.

Primary API references: [PyJWT verification and JWKS](https://pyjwt.readthedocs.io/en/latest/api.html),
[Turso create database](https://docs.turso.tech/api-reference/databases/create), and
[database-scoped token creation](https://docs.turso.tech/api-reference/databases/create-token).

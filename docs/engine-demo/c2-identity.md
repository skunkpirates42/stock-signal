# C2 identity and workspace boundary (#45)

The opt-in `demo.hosted` package is separate from `dashboard.app` and all local
B1–B5 routes. It does not start a server, enable hosted writes, provision a real
database, or invoke a replay. No broker dependency is imported.

## Identity and request contract

Install optional dependencies from `demo/hosted/requirements.txt`. Configure an
exact HTTPS issuer, client audience, JWKS URL, and application origin; no discovery
URL or key location comes from the request. `OIDCVerifier` accepts RS256 ID tokens
only at login, requiring issuer, subject, audience, expiry, issued-at and nonce.
It verifies authorized-party claims for multiple audiences. Issued-at, expiry and
optional not-before claims must be finite JSON numbers; booleans and strings are
rejected. Fractional NumericDate values are supported. PyJWT refreshes a
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
response, and 50 rows/page. Read/preflight bodies are rejected. Unknown-length
terminated bodies reaching the exact request ceiling are conservatively rejected
to avoid accepting framework-truncated input. A global 60/minute challenge budget bounds anonymous
login work. Durable fixed-minute limits default to 60/user and 120/workspace;
deployment may set explicit positive limits. Authorized handler failures consume
quota even when workspace changes roll back. Errors contain stable codes only,
without exception text, headers, tokens, paths, request bodies or tracebacks.

## Registry and provisioning

`migrate(connect, CONTROL)` installs the shared users, memberships, workspace
registry, challenges, sessions and rate-limit tables. Additive control migration 2
adds durable authorization-operation admissions, preserving the original version-1
checksum and data. The provisioning service
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
A request obtains a short `BEGIN IMMEDIATE` on the authoritative control database,
checks session/current membership and quotas, and commits a random operation ID in
`authorization_operations` as `active`. Only after this admission commit succeeds
may workspace work begin. The workspace transaction verifies UUID/checksum, performs
the handler, and materializes the bounded response. A confirmed commit or rollback
is then recorded as `completed` with its outcome in a fresh control transaction.
No live control connection or lock is relied on during workspace work.

Revocation uses the same control admission serialization to immediately deactivate
the membership and inspect its outstanding operations. New admissions then fail.
If any operation is `active` or `uncertain`, revocation commits the deactivation but
returns stable `revocation_pending` (409), never successful acknowledgment. Previously
admitted operations may finish while revocation is pending. The administrator must
retry revocation after completion/reconciliation; success requires no outstanding
operation for that user/workspace. An admission committing first therefore blocks
successful revocation until its workspace outcome is known; revocation committing
first blocks the admission. This holds even if the old control connection loses its
lock, because the fence is a durable row rather than a live transaction.

An interrupted process leaves an `active` record. A lost commit response or failed
rollback leaves `uncertain`; failed final control recording leaves an outstanding
record too. These fences have no automatic expiration and must not be cleared merely
because a process died, a lease elapsed or a retry returned no data. Reconciliation
must prove the authoritative workspace transaction outcome using stable C3 operation
identities and idempotency keys before a privileged, audited state change. There is
no reconciliation HTTP endpoint, default outcome or automatic retry in C2. Until C3
supplies outcome evidence/reconciliation, uncertainty keeps revocation pending. This
trades availability for a fail-closed successful-revocation guarantee.

Bytes already materialized may arrive over the network after successful revocation;
previously authorized data cannot be retroactively retracted. Session logout removes
the presented session and prevents future admissions; already admitted work may
finish. C3 workers need an explicit dispatch/cancellation policy, not a cached scope.

Only admission and completion transactions serialize globally; workspace operations
need not hold the control database lock. Active/uncertain records must be preserved;
completed-record retention/cleanup is a separate C7 policy. Handlers may not commit,
roll back or retain their connection; the boundary owns the transaction. Streaming,
replay and object downloads/uploads remain prohibited inside handlers. Artifact
handlers return bounded bytes from private C4 storage under an authorized parent row.
Staging must test remote admission/commit/rollback loss, timeouts, secret permissions
and throughput before hosted writes are enabled. Local fault fixtures establish the
ordering/fence behavior, not remote service reliability or deployed performance.

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
foreign keys, bounded responses, rollback and safe errors. Fault fixtures also cover
control connection loss, lost workspace commit responses with/without server commit,
failed rollback, process interruption, failed completion recording, migration-2
upgrade and malformed signed NumericDate types. Existing local route
tests remain the regression evidence for B1–B5.

This is implementation evidence, not hosted launch clearance. Production provider
integration, remote revocation/fault evidence, token/secret-store permissions, C3–C7,
independent Astra review and human security review remain launch prerequisites.

## Independent implementation review

PR #52 received a fresh read-only reviewer pass over the implementation and tests.
The reviewer found (1) failing authorized handlers could roll back quota counters,
and (2) GET bodies did not enforce the documented request ceiling. Both were fixed:
workspace failures are deferred until quota counters commit, and all methods perform
a bounded read with explicit unknown-length truncation denial. The reviewer reran
48 focused cases and separately reproduced the oversized chunked POST case, then
reported no remaining material findings. Two additional POST regression cases bring
the coordinator's initial focused suite to 50.

A second fresh standards/spec review found no standards breaches, but the security
review reproduced successful revocation before a workspace commit after control
connection loss, and acceptance of malformed signed temporal claim types. The fixes
replace lock-only ordering with durable admission/pending-revocation fences and
validate finite numeric claim types. Both reviewers independently checked the fixes and reported no remaining material
findings. The standards reviewer independently passed all 69 focused cases and ran
a local libSQL migration/admission smoke test. The full post-fix backend run passed
453 tests; three subsequently added admission/migration cases passed in the expanded
69-case focused run. `git diff --check` passed. These implementation reviews do
not substitute for production Astra/human security and remote staging launch gates.

Primary API references: [PyJWT verification and JWKS](https://pyjwt.readthedocs.io/en/latest/api.html),
[Turso create database](https://docs.turso.tech/api-reference/databases/create), and
[database-scoped token creation](https://docs.turso.tech/api-reference/databases/create-token).

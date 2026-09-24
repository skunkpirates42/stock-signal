# C2 authenticated identity and tenant boundary

C2 adds an opt-in Python boundary for the [hosted plan](../engine-demo-implementation-plan.md).
The local dashboard, SQLite stores, worker and paper execution remain unchanged.
`demo.hosted_api.create_hosted_app` is an application factory requiring explicit identity,
shared rate-limit and hosted data-service adapters. It has no local-store fallback and
is not wired into a public deployment. C3+ supplies the durable job/result service.

## Identity and request flow

`OIDCVerifier` accepts only RS256 signatures from a configured HTTPS JWKS endpoint,
with fixed issuer and audience. It requires subject, expiry, issuance time and nonce;
multi-audience tokens require a matching authorized party. Token-supplied URLs never
select a key endpoint. PyJWT's bounded JWKS cache expires after 300 seconds, refreshes
for an unknown key subject to a 30-second cooldown, and has no indefinite per-key cache.
An unavailable key fails closed; rotation can temporarily reject a new key during that
cooldown. See [PyJWT's verifier documentation](https://pyjwt.readthedocs.io/en/stable/usage.html).

The deployment's trusted OIDC callback uses `PostgresIdentity.begin_login` and
`finish_login`. A five-minute, single-use challenge stores the expected nonce server-side.
The callback must bind that challenge to the initiating browser using a Secure,
HttpOnly, SameSite cookie, validate OAuth state and use authorization-code flow with
PKCE. It must never accept a nonce selected by the submitted token. Provider redirects,
code exchange and callback routes are not implemented here; these are required wiring
before enabling this factory on a hosted deployment.

Successful verification upserts a UUID by `(issuer, subject)`; email is never identity.
It creates an opaque session, storing only session/CSRF hashes with an expiry no later
than the token expiry or one hour. The trusted callback sets the session as
`__Host-demo-session`, with `Secure; HttpOnly; SameSite=Strict; Path=/`, no Domain, and
returns the CSRF token only to that browser. Never place identity tokens in browser
storage or logs. `revoke` removes a session; expired and revoked sessions are denied.

Every HTTP operation resolves the session and current membership server-side. Exactly
one membership is required; zero or multiple memberships fail closed. There is no
client tenant switch. Owners and operators can submit/cancel; viewers can read.
Memberships and roles are checked again inside each operation transaction. A shared
transaction advisory lock protects that ordinary SELECT; a database statement trigger
takes the matching exclusive lock for every membership insert/update/delete/truncate.
This requires only SELECT membership privileges for the data role. Concurrent operations
share the lock; provisioning waits until they commit. If a change commits first, a fresh
READ COMMITTED statement sees it after the lock wait and denies stale authorization.
Connection factories must return fresh transactions. The global lock serializes rare
membership changes across users; operation transactions must remain short and bounded.
Administrative roles must keep the trigger enabled and lack trigger-management,
TRUNCATE and replication-role privileges. See PostgreSQL's
[transaction advisory lock semantics](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS). Provisioning memberships
is an audited administrative action, never an automatic consequence of login.

## Database and adapter contract

Apply `demo/migrations/001_hosted_identity.sql` using a migration role. It introduces
identity, tenant, membership, challenge/session, rate-counter and resource-ownership
records only. It creates no queue or replay store. Use a PostgreSQL connection factory
with transaction context semantics and tuple rows (for example psycopg connections).
No connection string is loaded or printed by this boundary.

Runtime connections must use a non-owner, non-superuser role without `BYPASSRLS` or
DDL/TRUNCATE grants. Provision only the grants each component needs: identity can
manage users/challenges/sessions, read memberships and update rate counters; the data
role reads ownership rows and inserts new ownership in authorized write transactions.
Keep administrative membership writes separate. Identity/session records are global
control-plane records and must not be accessible to tenant data services. The required
`data_connect` factory supplies a separately restricted role for operation transactions;
`connect` is the identity connection. Never give the data role session-table grants.

`hosted_memberships` and `hosted_resources` use forced RLS. Resource reads require
both the transaction tenant and an authenticated membership; inserts also require an
owner/operator role. A composite foreign key includes tenant, parent UUID and parent
kind, rejecting cross-tenant parents. Domain tables added in C3+ must reference these
composite identities and independently enable forced RLS. Register the ownership row
atomically with the domain record. Transaction-local settings never survive pool reuse.

Before invoking the data service, the HTTP boundary checks run/result ownership,
artifact parent ownership, and list cursor ownership against this registry. Unknown,
wrong-tenant and wrong-parent IDs all return `404 not_found`. The data service receives
only the authorized scope and transaction; it must apply explicit tenant predicates
and public A1 projections for every catalog/list/detail query. No global caches: use
`Scope.cache_key` for internal keys and never accept a client cache key. HTTP responses
are private and `no-store`, including errors and artifacts.

## HTTP and resource controls

Only the configured HTTPS host/origin is accepted. Commands require same-origin JSON
and the session's CSRF token; the app emits no CORS grants and denies preflight.
Tenant/user/owner header overrides and unexpected body/query fields are rejected.
All commands/status/result/artifact endpoints share the boundary. Errors are fixed
codes; exceptions, headers, tokens, paths and request bodies are never logged or echoed
by this application. Deployment access logs must also omit cookies, bodies and queries.

Shared PostgreSQL fixed-minute counters apply to user and tenant on every authenticated
request (defaults: 60/user and 300/tenant). A rejection returns 429 and Retry-After.
These counters work across application instances; an unavailable store denies service.
They allow a burst around a minute boundary. Ingress must additionally bound anonymous
login/challenge traffic, request/header sizes and connections. Schedule expiry cleanup
for challenges, sessions and old rate buckets; no unattended cleanup starts here.
Requests are capped at 4 KiB, JSON responses at 512 KiB and artifacts at 1 MiB. The
hosted factory imports no engine, broker or LLM and cannot execute a replay itself.

## Verification and remaining launch gates

Offline tests use synthetic identities, ephemeral RSA keys and private fixture resources.
They cover invalid signatures/claims, malformed tokens, key rotation, nonce consumption,
stable user UUIDs, session expiry/revocation, missing/ambiguous membership, role changes,
cross-tenant reads/cancellation/artifacts/cursors, CSRF/CORS, override attempts, cache
scope, shared counter semantics, bounds and sanitized errors. Repository SQL behavior
is exercised through an offline compatibility fixture; that fixture does **not** prove
PostgreSQL RLS or concurrency behavior.

Before deployment, run the migration and concurrent integration tests against actual
PostgreSQL under the exact runtime grants: omitted-predicate reads, forced RLS,
cross-tenant composite inserts, pool claim reset, duplicate login/session creation,
nonce races, both operation-first and revocation-first advisory-lock races, and atomic
rate counters. Verify a SELECT-only membership role can complete authorized operations. No PostgreSQL server was
available for this implementation's offline verification. Also complete the provider
callback/state/PKCE/cookie wiring, C3+ data adapters and end-to-end staging isolation
checks. Independent Astra review and human security review remain launch gates.

# Hosted engine demo boundary (C1)

This document is the design and launch contract for moving the local engine demo to a
hosted, authenticated service. It does not enable hosting or change the paper-only
local runtime. Public launch requires this plan, an independent Astra review, and a
human security review.

## Boundary and invariants

Vercel serves the dashboard and short request/response API calls only. It must not run
replays, hold broker credentials, or open SQLite files. A hosted API accepts a bounded
command, records it, and returns a stable opaque run ID. A durable worker performs the
replay outside the request lifetime and publishes a verified result. The deterministic
engine remains the source of direction and eligibility; hosted operation never adds
live or real-money execution.

The hosted service has three separately deployed trust zones:

1. **Web/API:** authenticates the request, applies authorization and rate limits, and
   writes a job transaction. It has no worker filesystem access.
2. **Queue/store:** PostgreSQL is the authority for tenants, users, jobs, attempts,
   result metadata, and idempotency keys. Row-level security (RLS) and explicit tenant
   predicates apply to every read and write.
3. **Worker/storage:** a short-lived isolated replay container claims a job, writes
   scratch data to an ephemeral volume, and uploads immutable result objects. It has a
   narrowly scoped database role and object-store prefix; it cannot submit broker orders.

The current B1–B5 local SQLite databases and filesystem results remain a supported
local mode. They are not exposed to the internet and are not treated as a hosted
multi-tenant implementation.

## Identity and tenant scoping

Use an OIDC-compatible identity provider. The API validates issuer, audience, signature,
expiry, and nonce according to the provider's documented JWKS rotation behavior. The
subject is the immutable external identity; an internal UUID user row is created on
first login. A tenant UUID is selected from a server-side membership table, never from
an arbitrary request field. Memberships carry an explicit role (`owner`, `operator`,
or `viewer`) and are checked before every command, status, result, or artifact read.

Every tenant-owned row contains `tenant_id`; composite foreign keys and database RLS
prevent cross-tenant references. The API sets a transaction-local tenant claim after
authentication and uses a separate migration/admin role for schema changes. Logs,
metrics, queue messages, object prefixes, and cache keys include tenant and user IDs
without including tokens or raw request bodies. A missing or ambiguous tenant is a
denial, not a default tenant.

## Durable queue and relational job store

PostgreSQL tables replace the local `demo_jobs` authority:

- `tenants`, `users`, and `memberships` establish identity and role scope;
- `runs` stores the stable existing run UUID, immutable request/configuration hashes,
  idempotency key, state, timestamps, and tenant ownership;
- `run_attempts` stores lease token, worker heartbeat, phase, retry count, and bounded
  failure code;
- `results` and `result_artifacts` store publication metadata and checksums, not file
  paths or mutable bytes.

The unique key `(tenant_id, idempotency_key)` is enforced in the database. Submission
checks that key before expensive dataset loading, then inserts the run and outbox event
in one transaction. Workers claim with `FOR UPDATE SKIP LOCKED`, a random lease token,
and a bounded lease. Heartbeats, completion, cancellation, and recovery require the
current token and are monotonic. A result publication and completion transition commit
atomically in the store; an expired worker can be retried only when no publication is
visible. Retry count and failure codes are bounded and fixed, so tracebacks, paths, and
credentials never become API data.

The queue consumer is at-least-once. Replay inputs and output publication are
idempotent by run UUID, attempt, and content hash. Dead-lettered jobs remain visible to
operators and are never silently discarded.

## Immutable object storage

Results are written to a tenant-scoped object prefix using a new random staging key.
The worker verifies the allowlisted file set, byte limits, MIME type, SHA-256, and
manifest relationships before completing the run. It then performs a conditional
publish/rename (or immutable versioned copy) and records object version IDs and hashes
in PostgreSQL. Published objects have bucket versioning, retention/lock policy, private
ACLs, and no user-controlled path components. The API streams only objects referenced
by an authorized result row, with bounded response sizes; it never accepts a storage
URL from the browser. Failed or abandoned staging objects are quarantined and cleaned
by a separate retention job after an audit interval.

## Stable public ID migration

The existing opaque UUIDs for normalized runs, results, and artifacts remain the public
IDs. During migration, import local rows into a staging schema, verify source manifests
and hashes, and insert using those IDs. Conflicts fail closed unless all immutable
identity fields and checksums match exactly; no ID is regenerated to hide a conflict.
Legacy source paths are migration inputs only and are never copied into public records.
Before import, an operator creates an audited mapping from each local `owner_id` to one
authenticated user and tenant UUID. The mapping includes the local owner string, derived
requester UUID, target subject, tenant, approver, and timestamp. Unmapped owners,
duplicate assignments, and conflicting membership records are rejected and quarantined;
the importer never guesses a tenant. Each imported row records source system, import
batch, original timestamps, schema version, and unknown provenance. A dual-read comparison must show identical envelopes,
ownership, checksums, and not-found behavior before local reads are retired.

## API and operational limits

API requests have explicit body, JSON, page, timeout, and response ceilings matching the
local B1–B5 contract. Authentication and authorization happen before expensive work.
Commands are same-origin JSON requests with CSRF protection where cookies are used;
token-based clients still require audience and tenant checks. CORS is an allowlist, never
`*` with credentials. Rate limits apply per user and tenant, and all errors use stable
codes without exception text. Vercel functions only enqueue, query, or cancel; they do
not wait for a replay or proxy arbitrary object URLs.

The worker supervisor runs as a non-root service with a narrowly scoped network allowlist:
PostgreSQL job claims/heartbeats and the private object-store endpoint only. It has
read-only application images, ephemeral scratch volumes, CPU/memory/process/time limits,
and a minimal environment. The replay child that imports the engine is a second, more
restricted process: it has no network namespace, no database or object-store
credentials, and communicates with the supervisor only through bounded local input and
output directories. The supervisor validates and uploads the child's output after it
exits. This split preserves durable queue access without giving replay code a network
path. Broker libraries and credential names are blocked in the child environment. The
only permitted execution mode is paper/local simulation; a hosted deployment has no
broker secret and cannot turn on live execution through a request parameter.

## Required isolation and recovery tests

Before public launch, CI and a staging deployment must prove:

- one user cannot read, cancel, or download another tenant's run or artifact;
- RLS still holds when API code omits a predicate, and tenant selection cannot be
  changed by a request body, cursor, cache key, or object key;
- concurrent identical submits create one run, while key reuse with a different request
  is rejected;
- worker lease expiry, retry, cancellation, duplicate delivery, and publish-before-die
  recovery preserve one stable result and never lose a visible result;
- staged objects are private, immutable, checksum-verified, bounded, and cleaned up;
- malformed JWTs, rotated keys, CSRF/CORS cases, oversized requests, and rate limits
  fail closed without leaking secrets;
- migration preserves IDs, envelopes, hashes, timestamps, unknown provenance, and
  not-found behavior against a fixed local fixture, including mapped, unmapped, and
  conflicting local-owner cases;
- a hostile parent environment and a replay container cannot submit broker orders or
  access unrelated tenant data.

Tests must use synthetic fixtures and fake identities. They must not require broker
credentials or submit any order.

## Rollout, observability, and rollback

Ship schema migrations backward-compatibly, deploy the read-only dual-read verifier,
then enable hosted writes for an allowlisted tenant. Record deployment revision,
schema version, worker image digest, queue latency, lease recoveries, failure codes,
object publication failures, authorization denials, and per-tenant rate-limit events.
Alerts must avoid request bodies, headers, tokens, paths, and tracebacks.

Rollback disables hosted writes and drains workers before restoring the prior API and
worker image. PostgreSQL migrations are forward-compatible; data is not deleted during
rollback. Object versions and the local source bundle are retained so a failed import
can be rechecked. Re-enabling hosted writes requires rerunning isolation and migration
checks against the exact deployed revisions.

## Explicitly deferred

Provider choice, production sizing, retention durations, user risk limits, billing,
custom domains, and any live broker integration are deployment decisions outside C1.
They must not be guessed in code or inferred from a successful local demo. C1 is
complete only when the reviewed plan and the isolation test suite are accepted; that
gate does not authorize public launch by itself.

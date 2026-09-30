# Hosted engine demo implementation plan (C1–C7)

This document is the design and launch contract for moving the local engine demo to a
hosted, authenticated service. It does not enable hosting or change the paper-only
local runtime. Public launch requires this plan, an independent Astra review, and a
human security review.

The selected hosted data architecture is one Turso Cloud **libSQL database per
workspace**, with a personal workspace for each user. A shared Turso libSQL control database
holds identity, memberships and the workspace registry. PostgreSQL implementation
work on `issue-46-hosted-postgres` remains historical evidence; its RLS and locking
results do not validate the Turso implementation. See the
[Turso proof and evidence](../experiments/turso/README.md).

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
2. **Queue/store:** a shared control database is the authority for identity, current
   memberships, provisioning state and workspace-to-database mappings. Each workspace
   libSQL database owns its jobs, attempts, results, artifacts and idempotency keys.
   Resolve the database server-side and verify its stored workspace UUID before use.
3. **Worker/storage:** a short-lived isolated replay container claims a job, writes
   scratch data to an ephemeral volume, and uploads immutable result objects. It has a
   database-scoped credential and object-store prefix; it cannot submit broker orders.

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

Each workspace database contains a fixed workspace UUID checked against the trusted
registry on every connection. A caller never supplies a database URL or credential.
Within a workspace, foreign keys enforce run/result/artifact parent relationships.
Use database-scoped credentials; keep provisioning credentials out of request and
replay processes. Verify the supported runtime permission restrictions in staging;
SQLite does not provide PostgreSQL RLS as a second authorization layer. Logs,
metrics, queue messages, object prefixes, and cache keys include tenant and user IDs
without including tokens or raw request bodies. A missing or ambiguous tenant is a
denial, not a default tenant.

## Workspace provisioning and migrations

C2 provisions one personal workspace per user through an idempotent workflow:
reserve workspace identity, create its database, apply checksummed migrations, verify
its workspace binding, then mark it ready. Interrupted provisioning resumes from
recorded state; a login cannot use a partially initialized database. Store credential
references in the registry and secrets in a deployment secret store. Do not put a
platform-wide token in worker jobs or browsers.

Record migration version/checksum per database and rollout status in the registry.
Migrate canaries first with bounded parallelism, resumable progress, drift detection
and backward-compatible application versions. Do not rely on Turso's deprecated
[Multi-DB Schemas](https://docs.turso.tech/features/multi-db-schemas). A migration
failure in one workspace must not mark the fleet complete. No data deletion on rollback.

The registry and workspace database do not share a transaction. C2 must specify and
test authorization when revocation races an in-flight operation; the earlier
PostgreSQL advisory-lock solution cannot be carried over. Until that contract is
reviewed, fail closed for missing/ambiguous membership and do not enable hosted writes.

## Durable queue and relational job store

For hosted mode, libSQL tables provide the durable job authority:

- the shared control database contains `workspaces`, `users`, `memberships` and
  provisioning records; tenant is the existing API term for workspace;
- `runs` stores the stable existing run UUID, immutable request/configuration hashes,
  idempotency key, state, timestamps, and tenant ownership;
- `run_attempts` stores lease token, worker heartbeat, phase, retry count, and bounded
  failure code;
- `results` and `result_artifacts` store publication metadata and checksums, not file
  paths or mutable bytes.

An idempotency key is unique within its workspace database. Submission
checks that key before expensive dataset loading, then inserts the run and outbox event
in one workspace transaction. Workers claim with a short `BEGIN IMMEDIATE`
read/update transaction, a random lease token and a bounded lease. Writers serialize
within one workspace; size transactions and benchmark busy handling accordingly.
Use direct remote access to the authoritative database, never offline sync for claims.
With Python `libsql==0.1.11`, isolate concurrent transactions in separate worker
processes: its blocking execute/commit calls hold the GIL and the thread-based probe
failed with `SQLITE_BUSY`. A different concurrency model requires new evidence.
Use the database clock and resolve uncertain commits through stable idempotency keys
and lease/result identities. Retry only when the transaction outcome is understood. Heartbeats, completion, cancellation, and recovery require the
current token and are monotonic. A result publication and completion transition commit
atomically in the store; an expired worker can be retried only when no publication is
visible. Retry count and failure codes are bounded and fixed, so tracebacks, paths, and
credentials never become API data.

The queue consumer is at-least-once. Replay inputs and output publication are
idempotent by run UUID, attempt, and content hash. Dead-lettered jobs remain visible to
operators and are never silently discarded.

A dispatcher consumes per-workspace outboxes and sends workspace/run identifiers to
an at-least-once work queue. Those messages are wakeup hints; the workspace job row
remains authoritative. Workers independently resolve trusted database bindings and
claim there. A scheduled reconciler discovers missed outbox notifications and expired
leases across ready workspaces, with a durable scan cursor, fairness, backpressure and
quotas. No atomic transaction spans queue delivery and workspace commit. C3 must
cover crashes at each boundary and measure the cost of fleet scanning.

## Immutable object storage

Results are written to a tenant-scoped object prefix using a new random staging key.
The worker verifies the allowlisted file set, byte limits, MIME type, SHA-256, and
manifest relationships before completing the run. It then performs a conditional
publish/rename (or immutable versioned copy) and records object version IDs and hashes
in the owning workspace database. Published objects have bucket versioning, retention/lock policy, private
ACLs, and no user-controlled path components. The API streams only objects referenced
by an authorized result row, with bounded response sizes; it never accepts a storage
URL from the browser. Failed or abandoned staging objects are quarantined and cleaned
by a separate retention job after an audit interval.

## Stable public ID migration

The existing opaque UUIDs for normalized runs, results, and artifacts remain the public
IDs. During migration, import local rows into a staging workspace database, verify source manifests
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
assigned-workspace libSQL job claims/heartbeats and the private object-store endpoint only. It has
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
- a workspace connection cannot read another workspace even without a tenant
  predicate; wrong registry mappings and cross-database credential use fail closed;
  request bodies, cursors, cache keys and object keys cannot select another database;
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
worker image. Workspace migrations are forward-compatible; data is not deleted during
rollback. Object versions and the local source bundle are retained so a failed import
can be rechecked. Re-enabling hosted writes requires rerunning isolation and migration
checks against the exact deployed revisions.

## Explicitly deferred

Identity/object-store/dispatch provider choice, production sizing, retention durations, user risk limits, billing,
custom domains, and any live broker integration are deployment decisions outside C1.
They must not be guessed in code or inferred from a successful local demo. C1 is
complete only when the reviewed plan and the isolation test suite are accepted; that
gate does not authorize public launch by itself.

## Delivery sequence and evidence limits

1. C1 (#27): review this architecture and the bounded remote proof.
2. C2 (#45): build trusted identity, durable workspace registry, provisioning and
   authorization semantics, including concurrent revocation.
3. C3 (#46): implement full workspace job/attempt/result/outbox persistence,
   dispatch, leases, heartbeat, cancellation and recovery.
4. C4 (#47): implement private immutable object publication tied to workspace rows.
5. C5 (#48): import stable IDs through explicit owner/workspace mappings.
6. C6 (#49): run the complete isolation/recovery suite on real Turso under exact
   deployed permissions, including cross-database token denial and network faults.
7. C7 (#50): prove fleet migration, allowlisted rollout, monitoring and rollback.

The proof is deliberately separate from production adapters. It uses synthetic
sessions, two databases and four simultaneous clients; it establishes a bounded
storage/routing result, not OIDC correctness, fleet capacity, artifact safety,
concurrent membership revocation or end-to-end C2–C7 completion. These issues remain
open. Independent Astra review and human security review remain required for launch.

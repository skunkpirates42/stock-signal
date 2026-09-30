# Hosted PostgreSQL job store (C3)

`demo/hosted_jobs.py` is an opt-in transactional store. The local B1–B5 SQLite
queue and its filesystem results remain supported. Importing this module does not
connect to PostgreSQL or start a worker.

## Provisioning

Apply `demo/migrations/001_hosted_identity.sql` first. Provision a `hosted_worker`
NOLOGIN role before applying `demo/migrations/002_hosted_jobs.sql`. Its login must
not be used by the API. Apply the migration with a distinct DDL owner; runtime
logins must be nonowners without `BYPASSRLS`, `TRUNCATE`, trigger alteration, or
schema modification rights. The migration is additive and does not read or rewrite
local SQLite. Rollback disables hosted writes and retains the new tables for audit;
it does not delete imported or published data.

The C2 API data role needs `SELECT, INSERT, UPDATE` on `hosted_runs`, `SELECT` on
`hosted_run_attempts`, `hosted_results`, and `hosted_result_artifacts`, `INSERT` on
`hosted_outbox`, and `USAGE` on its ID sequence. C2 already requires the scoped
`hosted_resources` grants. The worker role needs the migration's grants and only
the ability to claim jobs, update leases and states, and record verified result
metadata. A C4 object store adapter must verify and publish bytes before calling
`complete`; C3 never serves or uploads objects.

## Transaction contract

- Run API operations inside `PostgresIdentity.transaction(scope)`. Call
  `HostedJobStore.existing` with hashes of canonical request/configuration documents
  before expensive replay normalization. If absent, call `submit` in that
  transaction. It verifies both document hashes, adds the run resource and row, and
  inserts one outbox event atomically. A competing submit returns the winner's UUID
  when both hashes match; conflicting key reuse raises `IdempotencyConflict`.
- Run worker operations in separate short `READ COMMITTED` transactions using the
  `hosted_worker` login. `claim_next` uses `FOR UPDATE SKIP LOCKED`; `heartbeat`,
  `complete`, `fail`, and `confirm_cancelled` require the current lease token.
  Expired leases may be completed only before recovery changes the attempt.
- Outbox delivery is at least once. `pending_outbox` is a wakeup hint, and workers
  still poll `claim_next` so a lease recovery does not depend on a second event.
  Record delivery only after the consumer accepts the notification. Duplicates
  cannot create a second run because the run row is the authority.
- `complete` commits the result, artifacts, and completed state together. A retry
  with the same token, result ID and content hash is a no-op. A mismatched result
  is rejected. `recover_expired` requeues one unfinished attempt, then records a
  fixed `worker_lost` dead letter if the retry budget is exhausted.

Public failure codes are fixed in the schema and code. Do not put exception text,
paths, credentials, headers, or request logs in result documents. Deployment must
test these SQL transitions and RLS using a real PostgreSQL instance and separate
API/worker logins before hosted writes are enabled. The offline tests exercise the
adapter but cannot prove PostgreSQL row locks, policies, or migration syntax.

## PostgreSQL verification

The `.github/workflows/hosted-postgres.yml` PR gate starts a disposable PostgreSQL
17 service and runs `tests/test_hosted_jobs_pg.py`. The fixture creates a new
database and separate API/worker logins, applies migrations 001 and 002, verifies
the minimum grants, and removes only its own database and roles. It covers missing
tenant predicates, cross-tenant reads and updates, simultaneous submissions,
`SKIP LOCKED` claims, lease fencing and recovery, cancellation, publication
rollback, duplicate publication, and immutable result metadata. It uses synthetic
documents and does not start a replay worker or submit broker orders.

To repeat the gate locally, use a dedicated disposable PostgreSQL instance, install
`psycopg[binary]` and `pytest` in a Python 3.10+ environment, and run:

```sh
HOSTED_PG_TEST_DSN='postgresql://postgres:<test-password>@127.0.0.1:5432/postgres' \
  python -m pytest tests/test_hosted_jobs_pg.py -q --tb=short
```

Staging needs a separate run against its actual migration and runtime role grants,
plus the C6 isolation gate and recorded human security review, before hosted writes
are enabled. The PR gate does not activate a hosted service.

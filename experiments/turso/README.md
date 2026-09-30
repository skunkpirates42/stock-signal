# Turso workspace proof

Isolated proof on `turso-workspace-poc`, based on `origin/main` at `5a182bf`.
This does not replace the local application or implement the production hosted API.

## What it exercises

Two separate databases use the same SQLite schema and DB-API operations. A trusted
fake-session resolver selects a workspace through a server-owned registry. Each
database stores an immutable workspace binding, checked before every operation.
The probe tests denied cross-workspace reads, misrouting, unknown/revoked sessions,
viewer writes, four simultaneous identical submits, four competing worker claims,
expired lease recovery, stale-worker fencing, two-attempt exhaustion, duplicate
publication, and two restartable schema migrations. All fixtures are synthetic.

Short `BEGIN IMMEDIATE` transactions serialize writers within a workspace.
Lease timestamps come from the database. Completion after expiry is accepted only
until recovery invalidates that attempt's token. Completed results survive recovery.
Concurrent clients run in separate spawned processes; no client automatically retries an ambiguous
commit. Submission keys and matching publication retries resolve those ambiguities.

## Run locally

```sh
.venv/bin/python -m experiments.turso.probe
.venv/bin/python -m pytest tests/test_turso_proof.py -q --tb=short
```

The local command creates temporary databases and removes them afterward. The normal
pytest suite stays offline regardless of the caller's environment.

## Remote gate

Use two **empty, disposable Turso Cloud libSQL databases**, each with its own
database-scoped read/write token. This proof targets libSQL (SQLite fork), not the
new Turso engine. The official [Python driver guide](https://docs.turso.tech/sdk/python/quickstart)
distinguishes these engines. Use direct remote access, not an embedded replica or
offline sync, for authoritative job claims.

Install the optional driver with `.venv/bin/python -m pip install -r experiments/turso/requirements.txt`.
On Python 3.9/macOS ARM, the package builds from source and requires Rust and CMake.
Pip build isolation may require `CMAKE` pointing to the native CMake binary rather
than its Python launcher. Configure these
four names in an ignored `.env.turso-proof`, or export them in the calling shell:

```text
TURSO_PROOF_A_URL
TURSO_PROOF_A_TOKEN
TURSO_PROOF_B_URL
TURSO_PROOF_B_TOKEN
```

```sh
.venv/bin/python -m experiments.turso.probe --remote --env-file .env.turso-proof
```

The runner reads only these four variables, either from the explicitly named file
or the exported environment when no file is given. It refuses existing user tables and
identical endpoints, creates only `proof_*` tables, and leaves remote evidence intact.
A repeat can use fresh databases, or `--resume` to verify existing proof-only database
bindings and add a scenario with a new idempotency key while retaining prior rows.
Targeted claims model queue messages naming a run; they do not claim old proof jobs.
It never prints tokens, URLs or driver
exceptions. Exit 0 means all assertions passed; 1 means a failed check; 2 means
missing credentials. A local pass does not establish remote transaction or driver
correctness. Record the actual driver version and remote result before adopting.

## Adoption decision and remaining work

The remote proof passed using two Turso Cloud libSQL databases and four independent
worker processes. See [recorded evidence](evidence/remote-proof.json) and the
[updated hosted plan](../../docs/engine-demo-implementation-plan.md). The architecture
is selected for C1–C7 implementation. The PostgreSQL proof remains historical evidence;
this proof alone is not a public launch gate.

The initial remote run using Python threads failed with `SQLITE_BUSY`. The
[`libsql` binding](https://github.com/tursodatabase/libsql-python/blob/main/src/lib.rs)
blocks while holding the GIL in execute/commit, preventing a lock holder from making
progress while another thread waits for its database lock. The successful run uses
independent spawned processes and retains the failed run's synthetic rows. This is
a deployment constraint, not evidence that arbitrary threaded clients work. Runtime
driver or concurrency changes require the remote gate again.

The first remote attempt applied migrations 1 and 2 to both fresh databases before
failing at concurrent submission. The resumed successful run revalidated checksums
and workspace bindings. Offline tests additionally inject migration and transaction
failures to verify rollback and preservation of the original error.

Verification after the process-based repair: 12 focused tests and all 386 backend
tests passed. `git diff --check` passed. The remote evidence includes driver/runtime
versions and SHA-256 hashes of the exact store and probe sources tested.

Production still needs persistent provisioning/membership/credential management,
OIDC integration, defined semantics for revocation racing an in-flight operation,
database-scoped runtime permissions, network-failure testing, heartbeats and
cancellation, dispatch/outbox reconciliation across databases, fleet migration
rollouts, artifact authorization, quotas and operational benchmarks. The fake
resolver proves the routing contract only; it does not prove real login security.

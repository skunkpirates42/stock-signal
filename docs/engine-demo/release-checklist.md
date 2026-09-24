# B5 local demo release checklist

This checklist is the release record for issue [#26](https://github.com/skunkpirates42/stock-signal/issues/26).
It covers the local, paper-only B1-B4 demo. It does not activate a broker, publish a
strategy, or claim trading performance.

## Processes and data paths

Run Flask, Next.js, and the worker as three separate local processes. Use a dedicated
directory for a smoke or demonstration run:

```sh
RUN_ROOT=/tmp/stock-signal-demo
mkdir -p "$RUN_ROOT/worker"
cat > "$RUN_ROOT/demo.env" <<EOF
export DB_PATH=$RUN_ROOT/papertrader.db
export DEMO_ARTIFACT_DB_PATH=$RUN_ROOT/demo-artifacts.db
export DEMO_JOB_DB_PATH=$RUN_ROOT/demo-jobs.db
EOF

# terminal 1: Flask API (the B1-B3 authority)
RUN_ROOT=/tmp/stock-signal-demo; . "$RUN_ROOT/demo.env"; \
.venv/bin/python run_dashboard.py

# terminal 2: Next.js B4 UI
cd web && FLASK_API_URL=http://127.0.0.1:8000 ./node_modules/.bin/next dev

# terminal 3: one local worker
RUN_ROOT=/tmp/stock-signal-demo; . "$RUN_ROOT/demo.env"; \
.venv/bin/python -m demo.worker \
  --job-db "$RUN_ROOT/demo-jobs.db" \
  --root "$RUN_ROOT/worker"
```

Open `http://127.0.0.1:3000/run`, choose an available approved fixture, and submit it.
The browser talks to the dashboard only; it never supplies a path, cost, broker, or
strategy setting. Stop all three processes with Ctrl-C before backing up or rolling back.
The worker is intentionally one-host/one-worker. A second worker is not a supported
deployment mode.

The four persistent pieces are the operational journal (`DB_PATH`), the read-only A2
artifact index (`DEMO_ARTIFACT_DB_PATH`), the B2 job store (`DEMO_JOB_DB_PATH`), and
the worker root. The worker root contains private attempt directories, sanitized log
tails, and immutable published result directories. A result directory is only public
after its files are verified and atomically renamed into place.

## Smoke procedure and evidence

The offline fixture smoke uses the approved synthetic dataset and `base-v2` cost
profile. It submits through the Flask HTTP endpoint, runs the real worker, reads the
completed result, restarts the Flask app against the same three databases, and reads
the same run again. The worker was started with deliberately hostile values
(`BROKER=alpaca`, `LLM_PROVIDER=groq`, and fake Alpaca credentials); the child still
completed because the worker passes only its allowlisted local environment, blocks
broker/LLM imports and sockets, and refuses credential-bearing environments.

Recorded run on 2026-09-24 (runtime B4 head `7048f91`; the B5 commits after the smoke
are documentation-only):

| Check | Result |
| --- | --- |
| Submit | HTTP `202`, state `queued` |
| Run ID | `8650a23f-829e-46fc-8c15-7e5230c14653` |
| Worker | exit `0` |
| Completion | state `completed`, result present, 7 artifacts |
| Restart/reopen | state `completed`, same run UUID |
| Artifact after restart | artifact `17fa8644-f241-4ab2-9b89-9a54f084955c`; HTTP `200`, `application/json`, 2,497 bytes |
| Wall time | 4.389 seconds, including the worker and restart check |
| Broker/order isolation | no broker submission; the hostile parent environment did not reach the child |

The isolation claim is also covered by the offline worker tests
`test_isolated_child_cannot_reach_a_broker_llm_or_network`,
`test_child_refuses_to_replay_while_holding_a_credential`,
`test_hostile_parent_environment_does_not_reach_the_replay`, and
`test_child_environment_carries_no_credentials`. These tests assert blocked imports and
sockets, refusal when credentials are present, and the exact child environment
(`BROKER=local`, `LLM_PROVIDER=template`, with no credential variables). The smoke's
hostile parent run then exercises that same allowlist through the real worker path.

To repeat the same check without a browser, submit the five catalog IDs with an
`application/json` `POST /api/demo/v1/runs`, save the returned `run_id`, run the worker
command above with `--once`, and fetch `/api/demo/v1/runs/<run_id>` before and after
stopping and restarting the dashboard. A successful run is `completed` both times,
with a result and seven artifacts; a result visible before `complete` is a failure.

The fixture request is:

```sh
curl -sS -X POST http://127.0.0.1:8000/api/demo/v1/runs \
  -H 'Content-Type: application/json' \
  -d '{"strategy_id":"stock-signal","dataset_id":"6f1d0a52-3c1b-4f7e-9a51-0c6a1f4e2b10","window_id":"fixture-day-2","cost_profile_id":"base-v2","idempotency_key":"b5-smoke-20260924-02"}'
```

Run the worker with `--once`, record the returned UUID, stop and restart Flask, and
fetch the run and one artifact through the same API. This is the exact sequence used
to reproduce the recorded smoke above. Use a new idempotency key (or a fresh `RUN_ROOT`) for
each repetition; reusing a key on the same job database intentionally returns the old
run without executing it again.

## Fixed ceilings and behavior

These are implementation ceilings, not capacity or performance promises:

| Area | Ceiling/behavior |
| --- | --- |
| Run request body | 4 KiB (`MAX_RUN_REQUEST_BYTES`) |
| Indexed JSON record | 128 KiB |
| JSON API response | 512 KiB |
| One artifact response | 1 MiB |
| List page | 20 jobs/results by default and at most 50 for B2/A3 |
| Result-detail artifact references | 100 maximum; larger indexed results fail closed |
| Worker timeout | 900 seconds by default; `--timeout` may lower/raise it explicitly |
| Stop grace | 5 seconds before the process group is killed |
| Worker log | sanitized 64 KiB tail plus a truncation header; logs are never served |
| Retry | one retry after a lost worker, then `worker_lost` |
| SQLite lock wait | 30 seconds |

The worker has a wall-clock limit but no memory or CPU limit. It must not be treated as
a multi-user queue or exposed beyond the local operator boundary.

These are verified implementation ceilings, not throughput claims: boundary tests cover
the 4 KiB/1 MiB request and artifact limits, read-service tests cover the 128 KiB/512 KiB
JSON limits, and worker tests cover the 64 KiB log tail plus header, 5-second stop grace, and
two-attempt recovery. The only runtime measurement in this release is the 4.389-second
fixture smoke above; hardware and dataset size make that number local.

## Startup migration

There is no separate migration executable. `create_app` first calls the normal journal
initializer, which creates missing journal tables/indexes and adds missing signal/trade
columns while recording schema versions. `ArtifactIndex` and `JobStore` then create their
own tables with `CREATE TABLE IF NOT EXISTS`; the artifact index has one additive
compatibility migration where an older `demo_artifact_imports` table gets the
`projection_sha256` column with `ALTER TABLE ... ADD COLUMN` and an empty default.
These migrations are additive and do not rewrite old evidence. Start the dashboard once
against a disposable backup copy to apply them, then run the test suites before using
the release database.

## Backup

Stop the dashboard and worker first so SQLite WAL state is settled. Back up every
database and the worker root, preserving permissions and any `-wal`/`-shm` sidecars:

```sh
RUN_ROOT=/tmp/stock-signal-demo; . "$RUN_ROOT/demo.env"
BACKUP=/tmp/stock-signal-demo-backup-$(date +%Y%m%d-%H%M%S)
mkdir -p "$BACKUP"
for db in "$DB_PATH" "$DEMO_ARTIFACT_DB_PATH" "$DEMO_JOB_DB_PATH"; do
  cp -p "$db" "$BACKUP/"
  for suffix in -wal -shm; do
    if [ -e "${db}${suffix}" ]; then cp -p "${db}${suffix}" "$BACKUP/"; fi
  done
done
cp -a "$RUN_ROOT/worker" "$BACKUP/"
```

For a live system, stop first rather than copying an open database. Verify the backup
against a disposable copy of the backup: point all three processes at that copy, reopen
a known run, fetch one artifact and compare its bytes, then discard the disposable copy.
The B5 synthetic smoke has no imported A2 source bundle. If the artifact index contains
imports, list each path with:

```sh
RUN_ROOT=/tmp/stock-signal-demo; . "$RUN_ROOT/demo.env"
.venv/bin/python - "$DEMO_ARTIFACT_DB_PATH" <<'PY'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as db:
    for (path,) in db.execute("SELECT DISTINCT source_directory FROM demo_artifact_imports"):
        print(path)
PY
```

Copy each listed source bundle into the backup as well. For verification, use an isolated
host or temporarily move the original source directories aside, restore the copies at
the same absolute paths recorded in the index, and then compare artifact bytes. Do not
migrate or process jobs in the only rollback copy.

## Rollback

1. Stop the Flask dashboard, Next.js UI, and worker.
2. Preserve the current directory for forensic review; do not delete published results.
3. Check out the prior reviewed commit (or restore the prior application bundle).
4. Restore the three database files, captured `-wal`/`-shm` sidecars, any indexed source
   bundles at their recorded absolute paths, and the worker root as one unit.
5. Start the dashboard, run the backend/web checks below, and reopen a known completed
   run before accepting new submissions.

Rollback restores the local demo state only. It does not cancel broker orders because
the demo never creates broker orders. A queued or running job at rollback time should
be treated as interrupted: restart the worker with the restored job database and let
its lease recovery settle it before submitting another request.

## Verification gate

From the repository root:

```sh
.venv/bin/python -m pytest tests/ -q --tb=short
(cd web && ./node_modules/.bin/vitest run)
(cd web && ./node_modules/.bin/eslint .)
(cd web && ./node_modules/.bin/next build)
git diff --check issue-25-demo-run-ui...HEAD
```

Recorded on 2026-09-24 for the B5 release branch (the final commits after these checks
change documentation only):

| Check | Result |
| --- | --- |
| Backend | `374 passed, 2 warnings` in 111.69 seconds |
| Web tests | 20 files, `129 passed` |
| ESLint | passed with no errors or warnings |
| Next production build | passed; all B4 routes generated |
| Diff check | passed |

The release is acceptable only when all checks pass, the fixture smoke reopens after a
restart, and no credential or broker-order evidence appears in the worker or child.

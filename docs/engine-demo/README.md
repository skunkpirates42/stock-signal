# Engine demo v1 contract (A1)

This is the frozen initial read-model contract for [issue #17](https://github.com/skunkpirates42/stock-signal/issues/17).
It defines no importer, database migration, browser endpoint, execution catalog or
worker; those are later tickets. Saved research artifacts remain their original
formats and bytes.

## Schema and compatibility

[v1.schema.json](v1.schema.json) is a bundled JSON Schema Draft 2020-12 document with
local references only. Its root validates either one envelope or a nonempty array
of envelopes. Each envelope is `{schema_version: 1, data: ..., warnings: []}`;
`data.record_type` selects `strategy`, `dataset`, `normalized_run`, `result`,
`artifact` or `status`. The definitions can also be addressed independently, e.g.
`urn:stock-signal:engine-demo:v1#/$defs/unavailable`. Enable format checking for UUIDs
and timestamps. UTC means `Z` or `+00:00`, with inclusive start and exclusive end.

Public record shapes are closed. Metric names may be extended while each new metric
still has the required value, unit, basis and source pointer. A producer must not
silently add arbitrary raw source keys to a public record. A2 must preserve original
source bytes and unknown source fields internally, with explicit allowlisting before
public display. New required fields, vocabulary changes, and changed metric meaning
require a new schema version. This v1 has no request/worker implementation; B1/B2
must define their bounded command and transition validation against these read models.

## A2 saved-artifact index

`demo.artifacts.ArtifactIndex` is a local, read-only SQLite index for a selected saved
result directory. It indexes only its fixed protocol/comparison and per-run JSON/text
allowlist; raw bars, SQLite journals and arbitrary filenames are never indexed. Import
checks the protocol/comparison/per-run manifest consistency, declared dataset identity,
file hashes and A1 projection, while retaining raw JSON metadata (including unknown
source fields) internally. It does not claim to verify raw dataset bytes when those
bytes are intentionally excluded. Re-importing unchanged evidence for the same owner
is idempotent; changed evidence, path traversal and symlinked files fail closed.
The retrospective A1 projection is restricted to the two reviewed v2 protocol hashes;
synthetic imports require matching explicit source evidence and label. Artifact
resolution accepts an opaque indexed UUID and returns reverified bytes, not a
source path. A3 owns browser endpoints and any response-size policy.

`stock-signal` is the fixed strategy template key, an intentional exception to UUID
entity IDs. Window names, variant labels and cost policy IDs are descriptive keys,
never paths. Dataset, run, result and artifact IDs are opaque UUIDs. A1's validation
harness derives deterministic UUIDs for reproducible examples only; A2 owns durable
identity allocation. Artifact references contain checksums, byte sizes, MIME types
and owning result IDs, with no storage paths. Schema acceptance does not authorize
serving a file: A2/A3 must enforce ownership, allowlists, checksums and safe resolution.

## A3 local read API

The local dashboard exposes only versioned `GET /api/demo/v1/strategies`,
`/datasets`, `/cost-profiles`, `/research`, `/results/{resultId}` and
`/results/{resultId}/artifacts/{artifactId}` routes. JSON uses the fixed
`{schema_version: 1, data: ..., warnings: []}` envelope; records within catalog and
detail data use the A1 public projections. Catalog choices are descriptions of saved
source evidence only: datasets retain `approved_windows: []`, raw dataset bytes are
not indexed, and no response authorizes a replay or execution.

The server configures one local operator owner (`DEMO_OPERATOR_OWNER_ID`, default
`local`) and its separate A2 SQLite index (`DEMO_ARTIFACT_DB_PATH`); neither value
comes from a browser request. Result and artifact route IDs must be opaque UUIDs, are
owner-scoped, and artifacts are additionally scoped to their requested result. A3
never returns source paths or raw importer metadata. JSON pages and artifact bytes are
bounded; missing, changed, wrong-owner, or unsafe artifact references return `404`.

For newly registered strategies, `strategy_version` is the SHA-256 fingerprint of
the UTF-8 JSON object with exactly `template_version`, `source_sha256` and
`configuration_sha256` keys, sorted keys, compact separators, no ASCII escaping and
no NaN/Infinity (`json.dumps(..., sort_keys=True, separators=(",", ":"),
ensure_ascii=False, allow_nan=False)`). The configuration digest applies the same
serialization to the complete registered immutable strategy configuration. B1 must
retain that configuration with the template before registering executable versions.
Legacy files lack a declared immutable
template version, so A1 represents both version fields as unavailable. It separately
preserves saved revision, source SHA-256 and working-diff SHA-256 in normalized runs;
the current checkout revision is never substituted for saved provenance. A revision
with a working diff is not evidence of a clean build.

## B1 replay catalog and request builder

`demo.replay_catalog` is the only source of replayable inputs. It has two approved
datasets (the synthetic seeded fixture and the ignored local Alpaca IEX Jan-Aug 2026
file), each pinned to a file SHA-256 with fixed windows, plus two cost profiles
(`base-v2`, `adverse-v2`) matching the saved v2 protocols. There is no zero-cost
profile. A request has exactly `strategy_id`, `dataset_id`, `window_id`,
`cost_profile_id` and `idempotency_key`. Any other key, like a path or a cost value,
is rejected, and so is an unknown ID.

`build_replay_request` checks the dataset bytes against the catalog digest and the
metadata feed against the catalog's pinned feed. For each
symbol it selects the evaluation bars plus up to 120 prior bars (the trader's rolling
window), and it rejects a window with fewer than `WARMUP_BARS` warmup bars. It returns
an A1 `normalized_run` that records the file digest and the engine's selected-data
fingerprint, which matches the manifest `run_portfolio` writes for the same bars. The
record also carries the cost policy, accounting gaps and code identity. Market windows
are labelled retrospective and the fixture is labelled synthetic correctness.
`request_fingerprint` excludes the idempotency key, so B2 can detect key reuse with a
different request. The request also retains `strategy_configuration` (template
version, source digest and the full strategy settings, without cost and operational
settings). `strategy_version_for` recomputes `strategy_version` from it, so B2 must
store it with the job and the worker can check it before replaying.

## B2 local demo jobs

`demo/jobs.py` keeps run jobs in their own SQLite file (`DEMO_JOB_DB_PATH`, default
`demo-jobs.db` next to the journal). The engine journal and its `runs` manifests are
never touched. Flask exposes four routes, all scoped to the configured operator:

| Route | What it does |
| --- | --- |
| `POST /api/demo/v1/runs` | Validates the B1 request and queues it. Returns `202` with the status and a `Location` header. The same key and request return the same run; the same key with a different request returns `409 idempotency_conflict`. Rejections return `400` with the B1 code. The body must be JSON and at most 4 KB. |
| `GET /api/demo/v1/runs?limit=&cursor=` | Lists runs newest first. `next_cursor` is the last run ID on the page. |
| `GET /api/demo/v1/runs/{id}` | Returns the normalized run and its A1 status record. Unknown IDs and IDs owned by someone else both return `404`. |
| `POST /api/demo/v1/runs/{id}/cancel` | Needs a JSON content type (an empty `{}` body is fine). A queued run is cancelled straight away. A running run moves to `cancel_requested` and the worker finishes the cancel. Finished runs don't change, and asking again is safe. |

Errors these routes return themselves are JSON: `{"error": {"code", "message"}}`. The
codes are `not_found`, `invalid_request`, `unsupported_media_type`, `length_required`
(`411`, no Content-Length), `request_too_large`, `idempotency_conflict`,
`job_store_busy` (`503`, only when the database lock wait times out) and the B1
rejection codes. Flask's own errors, like `405` for a wrong method or `500` for an
unexpected fault, are still Flask's HTML pages. A `500` never echoes internal
exception text.

The worker side (B3) claims the oldest queued run with a lease token and sends
heartbeats with a coarse phase before the lease runs out. It then calls `complete`,
`fail` or `confirm_cancelled`. Every call needs the current lease token. A lease is
still valid at the exact instant it expires, and recovery takes it only after that.
`heartbeat`, `fail` and `confirm_cancelled` refuse an expired lease straight away,
even before recovery runs. `complete` still accepts an expired lease while the token
matches, because a matching token proves recovery hasn't run. That way a result
published just after the lease lapsed is recorded, not replayed. If a result was
published before the cancel took effect, completion wins.
`recover_expired_leases` handles a worker that stopped heartbeating:

- a pending cancel ends as `cancelled`;
- a first attempt goes back to the queue;
- a second attempt fails with `worker_lost`.

This only works for one host and one worker. WAL mode, a busy timeout and
`BEGIN IMMEDIATE` transactions keep two clicks from creating two runs and two claims
from taking the same run. Timestamps are read after the lock is taken, so
`created_at <= started_at <= ended_at` holds even when a call waits, as long as the
system clock doesn't step backwards. Lease expiry uses the same wall clock. It isn't a
multi-host queue.

### B2 decisions

- **Separate database file.** Jobs don't go in the journal or in the artifact index.
  That keeps web lifecycle state out of engine manifests. It also means turning on WAL
  for jobs doesn't change how the other two files are opened.
- **Run ID is the normalized run ID.** B1 already mints a UUID for the normalized run.
  The job reuses it, so the status and run records always point at each other.
- **Lease token, not worker ID.** Each claim gets a fresh random token. A worker that
  restarts under the same name can't act on an attempt it no longer owns. A late
  heartbeat can't revive an expired lease, but a late `complete` can still record a
  result while the token matches.
- **One retry after a lost worker.** No result is public until `complete` records it,
  so rerunning an unfinished attempt is safe. The status fields for starting, phase
  and heartbeat are cleared for the new attempt, while `attempt` keeps counting.
- **Completion beats a pending cancel.** Once a result is published, it's recorded as
  published. Cancel only settles a run that hasn't finished. A live worker records its
  result even after its lease lapses, as long as recovery hasn't run. B3 closed the
  remaining gap, a worker that publishes and then dies before `complete`, by writing
  the result rows in the same transaction as `complete` (see B3 below).
- **Idempotency lookup before the full build.** Submit checks the fields and the
  catalog IDs, which is quick because nothing is read from disk, then looks up the
  owner and key. A repeat click returns its run without reloading the
  dataset. That keeps the "same key and request, same run" promise even if the
  dataset changes on disk, and it skips the costly bar load. A new key still gets
  the full B1 check before it's queued.
- **Fixed failure summaries.** `fail` takes a failure code, not text, and each code
  maps to one fixed summary. No path, traceback or credential from a worker can reach
  the API. Details go to the worker's private, sanitized log (B3).
- **Submit and cancel must be JSON.** A cross-site page can send a form post to
  127.0.0.1, so loopback binding alone doesn't stop it. It can't send
  `application/json` without a CORS preflight. Flask answers the preflight but sends no
  `Access-Control-Allow-*` headers, so the browser blocks the request. The
  routes still don't check the Host header, so a DNS-rebinding page could reach them.
  That's true of every dashboard route today. B4's Next.js proxy checks the origin.
- **Rejections are `400` with the B1 code.** The UI (B4) reacts to `error.code`, not
  the status number. A reused key is the one case that gets its own status (`409`).
  Catalog IDs are checked first, so a reused key with an unapproved ID is a `400`, not
  a `409`.
- **Requester ID is derived.** The status contract needs a UUID requester, but the local
  operator scope is a name. `requester_id_for` derives a stable UUIDv5 from it.
- **No progress counts.** Progress stays `not_recorded` and the phase is coarse. The
  replay doesn't report trustworthy counts yet.

## B3 local demo worker

`python -m demo.worker` runs queued jobs one at a time. It reads the same job database
as the dashboard (`--job-db`, default `DEMO_JOB_DB_PATH` or `demo-jobs.db` next to the
journal) and keeps everything else under one directory (`--root`, default
`demo-worker/` next to the job database):

| Directory | What's in it |
| --- | --- |
| `attempts/<lease token>/` | Scratch space for one attempt: the job input, the child's raw log, its private `run.db` and the exported output. Deleted when the attempt ends. |
| `logs/<run id>/attempt-N.log` | The sanitized tail of the child's output, mode `0600`. Never served. |
| `results/<result id>/` | Published results. Nothing in here changes after it's renamed into place. |

`--timeout` sets the replay limit in seconds (default 900), and `--once` runs at most
one job and exits. Before each claim the worker runs `recover_expired_leases`, so a
restarted worker picks up where a dead one left off.

### How a job runs

1. The worker claims the oldest queued job and writes the stored request, normalized
   run and strategy configuration into a fresh attempt directory.
2. It starts `python -E -s -m demo.replay_child <attempt>` in its own process group,
   with the repo as the working directory. The child's environment is built from
   scratch: `PATH`, `LANG`, the three settings that feed the strategy fingerprint
   (`SESSION_POLICY`, `BAR_LATENESS_SECONDS`, `ACCOUNT_NAMESPACE`), the cost profile's
   values, `BROKER=local`, `LLM_PROVIDER=template`, and journal paths inside the
   attempt directory. No credential or other variable from the worker comes along,
   and `-E` ignores `PYTHONPATH`. `config` normally loads the repo `.env` on import,
   so the child turns `load_dotenv` into a no-op first, and it refuses to replay
   (`validation_failed`) if any variable whose name contains `KEY`, `SECRET`, `TOKEN`,
   `PASSWORD` or `URL` is present.
3. Before importing the engine, the child blocks the `alpaca`, `trades.alpaca_broker`,
   `anthropic`, `groq` and `openai` imports and replaces socket connects with an error.
   It then rebuilds the request through B1 and refuses to run (`validation_failed`) if
   the selected data, the strategy version, the cost settings or the broker no longer
   match the queued run. A missing dataset is `input_unavailable`.
4. While the child runs, the worker heartbeats with the phase the child reports. A
   cancel request stops the process group (`SIGTERM`, then `SIGKILL` after 5 seconds)
   and settles the job as `cancelled`. Hitting the time limit does the same and fails
   the job with `timeout`. A lost lease stops the child and walks away without
   touching the job, because recovery already owns it. Any other non-zero exit is
   `execution_failed`.
5. When the child exits cleanly, the worker checks the output. All seven files must
   be there as regular files, the manifest must match the queued run's selected data,
   feed and cost policy, and the A1 `result` and `artifact` records built from it
   must pass the schema. Anything else fails the job with `artifact_invalid`.
6. The worker writes the files into `results/.staging-<id>/`, fsyncs them, renames the
   directory to `results/<id>/` and then calls `complete`, which records the result
   and artifact rows in the same transaction that marks the job completed.

`GET /api/demo/v1/runs/{id}` now carries `result` (the A1 result record) and
`artifacts` for a completed job; both are `null` and `[]` otherwise.
`GET /api/demo/v1/runs/{id}/artifacts/{artifactId}` serves one file. It rechecks the
checksum and size, opens the file without following symlinks, and caps the size at
1 MB. An unknown, wrong-owner, unfinished or tampered artifact is a JSON `404`, and
an oversized one is `413 content_too_large`.

### B3 decisions

- **Results live in the job database, not the A2 index.** The A2 importer takes a
  whole research directory (protocol, comparison and runs), mints its own run IDs, and
  only labels two reviewed scenarios as retrospective. A job already has its run
  record and ID, so its result sits next to it. A3's `/results` routes still list only
  imported research.
- **Result rows commit with `complete`.** A result is visible only once the job is
  completed, and the job is completed only when the result is recorded. A worker that
  dies after the rename but before `complete` leaves an unreferenced directory, and
  recovery replays the job into a new one. Nothing partial is ever served. The cost
  is that orphaned directories aren't swept yet.
- **A cancel that arrives before publishing wins.** The worker checks one last time
  (the `verifying` heartbeat) before it publishes. After that, completion wins as in B2.
- **Raw bars aren't published.** The replay also exports `bars.json`, but it's left
  in the attempt directory, the same as A2's rule for raw bars. The published files
  are the manifest, metrics, trades, accounting, cash flows, report and feed metadata.
- **The child re-validates.** The dataset or code can change between submit and
  claim. The child rebuilds the request and compares digests rather than trusting
  the stored copy, so a stale job fails instead of producing a result under the
  wrong label.
- **Blocking imports as well as forcing `BROKER=local`.** The replay path already
  uses the local paper broker and template synthesis. The import and socket blocks
  are a second line, so a future code path can't reach a broker or LLM from a demo
  job by accident.
- **Logs stay private.** Failure summaries stay fixed per code. The kept log is the
  last 64 KB with the attempt path, repo path and home directory replaced, and with
  any worker environment value whose name contains `KEY`, `SECRET`, `TOKEN`,
  `PASSWORD` or `URL` redacted. `failure.log_artifact_id` stays unavailable.
- **Limits.** The worker enforces wall-clock time only; there's no memory or CPU cap
  on the child. The child's raw log can grow without bound while it runs, but only
  its last 64 KB is kept. A worker killed with `SIGKILL` can't stop its child. The
  orphan keeps running in its attempt directory, but it can't publish anything,
  because only the worker publishes.

## Provenance and unavailable values

Provenance has separate axes: `source` (`backtest`, `live`, `unknown`), `execution`
(`local_simulation`, `paper`, `unknown`), and `evaluation` (`retrospective`,
`synthetic_correctness`, `prospective`, `unknown`). Historical, retrospective and
synthetic booleans are explicit, with consistency constraints. No real-money value
exists. Label evidence is required. No promotion/activation field or action exists.

A saved window role of `holdout` is retained unchanged. The January–August 2026
base/adverse scenarios are labelled historical and retrospective using the
[accounting contract](../experiments/accounting-contract.md), regardless of the historical role
name. Holdout status requires an explicit prospective registration/coverage record;
these examples use unavailable / `not_registered`. It is never derived from dates.
Synthetic data is explicitly labelled by the fixture declaration, not a market
performance claim. Empty `approved_windows` conveys no execution approval.

Every potentially absent datum uses an availability object:

```json
{"availability":"unavailable","value":null,"reason":"not_modeled","detail":"Short borrow is excluded from this saved report."}
```

An available datum has a non-null value, `reason: null`, and optional explanatory
`detail` (present, but nullable). An unavailable datum must have null value, a
nonempty explanation and one reason: `not_recorded`, `not_modeled`, `not_applicable`,
`missing_artifact`, `unverified`, `unknown_legacy` or `not_registered`. A measured or
saved zero is available; an omitted amount is never zero. Partial accounting has a
nonempty unresolved list; complete accounting requires that list to be empty. An unverified dataset hash/coverage record does not imply
the source bars are available for replay.

## Metric mapping and accounting

Every scalar metric carries an observation, unit, nonempty basis and a source JSON
pointer when available. Pointers address a logical source bundle with keys
`comparison` and `marked_review`; they are not filesystem paths or browser URLs.
An available by-regime object requires `basis`, `unit: "USD"`, `source_pointer` and
`values`. Each named regime has exactly `n` and `wins` (nonnegative integer counts),
`pnl` (a number in USD under the saved basis), and `win_rate` (a numeric fraction
between zero and one). The wrapper's USD unit applies to P&L. All source numbers
remain unchanged. Required named scalar metrics have fixed units enforced directly
by JSON Schema; extensions still require an explicit basis and unit.
Consumers display values as supplied by Python and must not recalculate P&L.

| Normalized value | Saved source | Basis / limitation |
| --- | --- | --- |
| `realized_net_pnl`, `gross_pnl`, `recorded_costs` | comparison row `metrics.total_pnl`, `gross_pnl`, `costs` | Closed trades; exact saved `metrics.metric_basis` retained |
| `realized_max_drawdown` | `metrics.max_drawdown` | Realized sequence, not marked drawdown |
| `closed_trades`, `censored_positions` | `metrics.n_closed`, row `censored_positions` | Open positions remain censored for realized results |
| `marked_net_pnl`, `marked_max_drawdown` | matched marked-review row `marked.marked_net_pnl`, `max_marked_drawdown` | Latest completed close, entry costs deducted, no hypothetical exit cost |
| `marked_net_per_session`, `max_gross_exposure` | matched marked-review fields | USD/session and USD respectively; preserve marked valuation policy |
| `borrow_cost`, `dividend_cashflow` | Absent modeled amounts | Unavailable / `not_modeled`, accounting incomplete |
| `spread_cost`, `slippage_cost`, `fees` | Absent separate amount totals | Unavailable / `not_recorded`; aggregate `costs` and policy rates cannot supply these totals |

Marked-report limitations are preserved verbatim, including excluded dividends,
borrow and taxes, stale IEX marks, and observation-weighted exposure. Realized and
marked amounts keep independent basis labels; neither is labelled fully accounted
net profit. Saved diagnostics limitations are also retained. Underlying source
artifacts preserve fields not yet projected (including uncertainty and concentration).
The current accounting implementation/version does not retroactively upgrade old
artifacts. An omitted accounting policy remains unknown, with explicit gaps.

The input-file checksum and selected-data checksum are distinct fields. The latter
is the engine's saved data fingerprint, not a claim that hashing a serialized
`bars.json` file yields the same digest. Observed first/last bars are distinct from
the requested window; last observed bar is an observation timestamp, not an exclusive
bound. Saved protocol coverage is copied, not reconstructed. Dataset metadata remains
`partial` until an importer verifies the full catalog requirements.

## Status semantics

`status.origin = saved_artifact` is a completed saved result reference, not a claim
that a queue job ran. Missing lifecycle times, attempt, heartbeat and engine run ID
remain unavailable; file modification times are not substituted. Completed status
requires an available result UUID. Failed status requires stable, bounded failure
details; other states do not expose a result or failure record. Cancellation details
record a request, not proof of completion. B2 owns transition, chronology, progress,
retry and cancellation-race invariants. Progress counts are nonnegative integers
with `bars`, `sessions` or `artifacts` units; unknown totals use availability objects.
Summaries/logs must be sanitized server-side;
the schema cannot prove arbitrary strings contain no credentials.

## Fixtures and verification

[fixtures/synthetic-source.json](fixtures/synthetic-source.json) is a portable,
hand-authored legacy-shaped source bundle. It intentionally has a known realized zero
and omits marked review, code identity, accounting version, cost decomposition,
dataset hash/coverage and job timestamps. It is not an engine run and does not alter
the existing `tests/fixtures/bars.json` data. [validate.py](validate.py) produces
ephemeral v1 examples from it and verifies the schema plus nonempty windows and
unresolved accounting amounts. It writes no files and imports no engine/broker code.
Its `validate` helper accepts either one envelope or a nonempty envelope array,
matching the schema root.

Install the validation-only dependency once, then run offline checks from the repo:

```sh
.venv/bin/python -m pip install -r docs/engine-demo/requirements-validation.txt
.venv/bin/python docs/engine-demo/validate.py
.venv/bin/python docs/engine-demo/validate.py --saved research-output/alpaca-iex-2026-base-v2 research-output/alpaca-iex-2026-adverse-v2
.venv/bin/python -m pytest tests/test_engine_demo_contract.py -q --tb=short
git diff --check
```

For each of the two saved scenarios, the compatibility check validates all eight
window/variant projections, joins marked rows by window and variant, compares
per-run metrics/diagnostics, checks protocol/manifest input identities and cost
settings, and hashes all 27 consumed files before and after. It preserves all source
values; no replay, profitability calculation, raw bars download or source rewrite
occurs. This is a schema compatibility check, not full A2 import validation or a
fresh financial reconciliation. It does not verify the underlying dataset bytes,
SQLite journals, or all downloadable files. Missing optional local scenarios are
reported as skipped in pytest; explicit CLI paths must exist and never silently skip.

Negative tests cover missing basis, lost retrospective/synthetic labels, wrong value
types, unavailable amounts changed to zero, reversed/empty windows, missing completed
result references and unsafe artifact fields. JSON Schema alone cannot establish
the truth of evidence, cross-record ownership, checksum correctness or strategy
validity; source checks and later importer validation remain necessary.

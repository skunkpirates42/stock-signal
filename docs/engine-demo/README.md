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
different request. The strategy fingerprint ignores cost and operational settings.

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

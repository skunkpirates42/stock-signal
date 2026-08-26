# Next.js Dashboard — Design

Date: 2026-08-26
Status: approved for planning

## Goal

Replace the Flask dashboard UI with a Next.js (App Router, TypeScript) frontend that
surfaces per-signal reasoning and the indicator votes behind each decision. Two audiences:
personal research use, and a portfolio piece for a job search.

The Python signal engine, data layer, and paper executor are not being rewritten. The
backend changes listed in Phase 0 are the minimum required to make the dashboard honest.

## Audit findings

Two problems were found while reading the existing system. Both shape the design.

### 1. Stored reasoning is template text, not model output

`signals/llm_synthesis.py` calls Claude only when `ANTHROPIC_API_KEY` is set and falls back
to a deterministic template on any failure. Every `reasoning` value currently in
`papertrader.db` is template output. The `synthesis_source` field distinguishing the two is
computed in memory and then discarded — there is no column for it, so the provenance of any
stored string is unrecoverable.

`live/trader.py` calls `synthesize()` only when `direction != "WAIT"`, so WAIT signals have
never had reasoning. `backtest.py` never calls it at all.

### 2. `papertrader.db` contains backtest data

A `backtest.py` run on 2026-06-10 wrote into `papertrader.db`. `backtest.py` skips WAIT
signals, never calls `synthesize()`, and writes one trade per signal — which matches rows
1–135 exactly: 135 signals, 135 trades, zero WAIT, all reasoning blank.

`analytics/metrics.py::load_closed_trades` blends these with the 20 real trades into a
single equity curve ordered by close time. Effect on the headline numbers:

| Scope | closed | win rate | expectancy | total P&L |
|---|---|---|---|---|
| All rows (what the Flask UI shows) | 150 | 31.3% | −$0.72 | −$108.19 |
| Backtest rows (id ≤ 135) | 135 | 32.6% | +$0.84 | +$113.70 |
| Live rows (id > 135) | 15 | 20.0% | −$14.79 | −$221.89 |

The 15-trade live sample is far below the 50-trade floor set in `CLAUDE.md` and supports no
conclusion about signal quality. The problem being fixed here is data integrity, not
performance.

`backtest.db` is a separate file and is unaffected. The ~2,500-trade validation finding in
`README.md` stands.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Data access | Next.js server components fetch the Flask API | Keeps `analytics/metrics.py` the single definition of expectancy, drawdown, and R-multiple. Reimplementing them in TypeScript would create two sources of truth for the numbers the project exists to validate. |
| Deployment | Local only; Vercel deferred | Vercel cannot reach a SQLite file on the developer's machine. Deferred rather than solved. |
| Contamination | Tag with a `source` column | Non-destructive and reversible. Avoids a magic id cutoff in the frontend and prevents recurrence. |
| LLM provider | `anthropic` \| `groq` \| `template`, env-selected | User preference for provider flexibility. Implemented as a dispatch inside one function, not an adapter layer. |
| Backfill scope | The 269 live signals, including WAIT | Backtest rows are hidden by default in the UI; generating rationale for them is spend with no reader. |
| Backfill model | `claude-haiku-4-5` via Batch API | ~$0.11 for 269 signals. Cheaper than Groq's `qwen/qwen3.6-27b` ($0.60/$3.00, and flagged preview) with no added dependency. |

### WAIT-signal rationale stays out of the bar loop

The backfill covers WAIT signals, but `live/trader.py` keeps calling `synthesize()` only for
actionable signals. Calling it on every bar would put a network round-trip in the hot path
for 8 tickers × 78 bars/day, mostly to explain non-events, contradicting the "LLM fires only
on a trigger" decision in `CLAUDE.md`.

Going-forward WAIT rationale is therefore generated out-of-band by re-running the backfill
script, which is idempotent and fills blanks only. A post-market hook is a later option, not
part of this work.

## Architecture

```
stock-signal/
├── signals/ data/ trades/ analytics/ live/     unchanged
├── db/logger.py                                + source, synthesis_source columns
├── signals/llm_synthesis.py                    provider dispatch
├── dashboard/app.py                            + limit param on /api/signals
├── scripts/backfill_reasoning.py               new, one-off
└── web/                                        new
    ├── src/app/
    │   ├── page.tsx                overview            (server)
    │   ├── signals/page.tsx        history + filters   (server shell)
    │   └── positions/page.tsx      open + fills        (server)
    ├── src/lib/
    │   ├── api.ts                  typed fetch against Flask — the only I/O seam
    │   ├── types.ts                Signal, Trade, Metrics, AlertEvent, VoteRow
    │   ├── indicators.ts           parse indicators_json → VoteRow[]
    │   ├── filters.ts              filter predicates over Signal[]
    │   └── format.ts               currency, percent, R-multiple, timestamps
    └── src/components/             presentational, plain props only
```

Server components fetch Flask over `localhost`, parse into typed domain objects in `lib/`,
and pass plain props down. Client components are used only for filter controls, Recharts,
and expand/collapse. No fetching and no domain rules inside JSX.

`lib/api.ts` is the single seam. Moving later to a committed snapshot or hosted Postgres
changes that file and nothing else.

Server-to-server fetching means no CORS dependency is needed on the Flask side.

## Phase 0 — backend

Ordered. Each step is independently verifiable.

### 0.1 Schema migration

Add to `db/logger.py`, in `_SCHEMA`/`_TRADES_SCHEMA` and in `_MIGRATIONS` so existing
databases pick them up:

- `signals.synthesis_source TEXT` — `template`, or `provider:model` (e.g. `anthropic:claude-haiku-4-5`)
- `signals.source TEXT` — `live` | `backtest`
- `trades.source TEXT` — `live` | `backtest`

`log_signal` and `log_trade_open` persist `source`; `log_signal` also persists
`synthesis_source`. Default `live` when unset.

### 0.2 Tag existing rows

One-off, in the same script as the backfill behind a `--tag-source` flag:

```sql
UPDATE signals SET source = CASE WHEN id <= 135 THEN 'backtest' ELSE 'live' END WHERE source IS NULL;
UPDATE trades  SET source = CASE WHEN id <= 135 THEN 'backtest' ELSE 'live' END WHERE source IS NULL;
```

The id cutoff is used exactly once, here, and never reaches the frontend.

### 0.3 `backtest.py` stamps its writes

`backtest.py` sets `source='backtest'` on every signal and trade it logs, so a future run
pointed at the wrong `DB_PATH` is visible rather than silent.

### 0.4 Provider dispatch

`signals/llm_synthesis.py` gains `LLM_PROVIDER` handling:

```python
def synthesize(signal):
    provider = config.LLM_PROVIDER
    if provider == "anthropic":
        text, source = _anthropic_reasoning(signal)
    elif provider == "groq":
        text, source = _groq_reasoning(signal)
    else:
        text, source = _template_reasoning(signal), "template"
    signal["reasoning"], signal["synthesis_source"] = text, source
    return signal
```

Three module-level helpers, one dispatch, no classes and no registry. Both provider helpers
fall back to the template on any exception, preserving current offline behavior. Groq is
OpenAI-wire-compatible and uses the `openai` package against `https://api.groq.com/openai/v1`.

New config: `LLM_PROVIDER` (default `anthropic`), `LLM_MODEL` updated from the superseded
`claude-sonnet-4-20250514` to `claude-haiku-4-5`, `GROQ_MODEL` (default `qwen/qwen3.6-27b`).
New env: `GROQ_API_KEY`. New dependency: `openai`.

### 0.5 Backfill script

`scripts/backfill_reasoning.py`:

- Targets `source='live'` signals with null/empty `reasoning`.
- Idempotent — fills blanks only, safe to re-run.
- `--dry-run` prints counts and a sample prompt without calling any API.
- `--limit N` for a small paid smoke test before the full run.
- Uses the Batch API when the provider is `anthropic`.
- Writes `synthesis_source` alongside every `reasoning` it sets.

Prompt keeps the existing constraint: summarize, never re-decide. WAIT signals get a prompt
variant explaining why the engine stood aside.

### 0.6 Flask endpoint

`/api/signals` accepts `?limit=` (currently hardcoded to 100; 269 live signals exist) and
`?source=`. Both default to current behavior when absent.

## Phase 1 — frontend

### `/` overview

Stat row (win rate, expectancy, total P&L, max drawdown, closed/open counts), equity curve,
by-regime and by-ticker tables.

Two honesty affordances, both non-optional:

- **Provenance band.** States which rows the numbers cover, defaulting to live-only, with a
  toggle to include backtest. Without this the headline number is ambiguous.
- **Sample-size and cost band.** Below 50 closed trades, the expectancy figure is rendered
  as provisional per `CLAUDE.md`. Expectancy is shown net of an adjustable per-trade cost
  assumption alongside gross, because `README.md` concluded the gross edge sits below
  realistic transaction costs.

### `/signals`

Filter bar (ticker, direction, date range, min confidence, source) over one fetch, filtered
client-side. Correct at 269–404 rows; the predicates move server-side past a few thousand.
This limit is documented at the call site.

Each row expands to show:

- Reasoning text, labeled with its `synthesis_source`
- The six votes parsed from `indicators_json`, each with its raw value and threshold
- Entry/stop/target/R:R with the ATR arithmetic shown
- A link to the resulting trade, when one fired

`indicators_json` is populated on all 404 rows including WAIT, so the vote table always
renders even where reasoning is absent.

### `/positions`

Open positions and recent fills. No live unrealized P&L — the dashboard has no quote feed,
so distance-to-stop is shown as of entry rather than fabricating a current price. The five
stale positions open since 2026-07-15 are labeled as such.

## Testing

- Python: extend `tests/` for the provider dispatch, the migration, and the backfill's
  blanks-only behavior. The existing 58 tests must stay green and will be run, not assumed.
- TypeScript: Vitest over `lib/` pure functions — `indicators.ts`, `filters.ts`, `format.ts`.
  No component mounting, no DOM, no Playwright.

## Deployment path (decided, not built in this phase)

Not building it now is a scheduling choice, not an open question. The answer below is
settled so the design does not paint itself into a corner, and so it can be explained on
demand.

**The deployed build reads a committed snapshot; local dev reads the Flask API.**

`lib/api.ts` gets two implementations behind one set of return types, selected by an
environment variable:

| Environment | Source | Data |
|---|---|---|
| local dev | Flask on `localhost:8000` | current, live |
| Vercel build | `snapshot.json` committed to the repo | as of last export |

The snapshot is produced by a Python script that calls `analytics.metrics.compute_metrics`
and serializes the result alongside the signal and trade rows. **The metrics are computed in
Python and baked in — TypeScript never recomputes them.** This is the same single-source-of-
truth decision as the Flask path, preserved across the deployment boundary rather than
abandoned at it.

Consequences:

- The Vercel build is fully static. No serverless functions, no database, no cold starts,
  nothing to keep awake. Free tier, indefinitely.
- Refresh is `python scripts/export_snapshot.py && git push`.
- Payload is small: 269 signals plus 155 trades plus a metrics object is well under 1 MB.
  Including the 2,510-row `backtest.db` corpus is optional and would exercise the
  provenance filter with real volume — a better demo, at a few MB.
- The deployed page must label itself a snapshot with its export date. Presenting stale data
  as live would contradict the honesty affordances that are the point of the UI.

### Why not hosted Postgres

Supabase or Neon on a free tier would make the deployment genuinely live, and is the more
impressive architecture on paper. It was rejected for this project because it requires
reworking `db/logger.py` off `sqlite3`, requires the local runner to have network access to
write, and — decisively for a link on a résumé — free-tier projects auto-suspend after
inactivity. A portfolio URL that is slow or broken when a recruiter opens it is worse than a
static one that always loads. If the engine ever runs continuously on a host, this becomes
the right answer and `lib/api.ts` is the only file that changes.

### The constraint this places on Phase 1

`lib/api.ts` must expose functions returning fully-typed domain objects with no Flask-shaped
details leaking past it, and no component may assume data is current. That is already the
design; this section is why it is non-negotiable.

## Non-goals

Vercel deployment *in this phase* (the path is settled above); WebSocket or streaming
updates; auth; real-time unrealized P&L; changes to `backtest.db`; rewriting or deleting the
Flask app, which keeps working throughout; any change to signal logic or thresholds.

## Risks

- **Two processes in dev.** `python run_dashboard.py` plus `pnpm dev`. Documented, not
  managed by a supervisor.
- **Groq's Qwen model is preview.** Groq's docs state preview models "should not be used in
  production" and may be discontinued at short notice. The template fallback covers its
  disappearance; the Anthropic path is the default.
- **Live sample is 15 trades.** The dashboard will show discouraging live numbers that are
  statistically meaningless. The sample-size band exists specifically so this is not
  misread — by the author or by anyone reviewing the project.

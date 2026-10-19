# UI clarity plan

The dashboard was written for its author as the auditor. Every screen carries the full
provenance record inline: status diagnostics above each title, the same caveat under every
metric, internal read-model names in user copy. Nothing is wrong, but the one number a
reader came for is hard to find.

This plan makes each screen summary-first without hiding anything. The constraint from
`CLAUDE.md` still holds: unknown stays unknown. Caveats move, they don't disappear, and an
unavailable value is never shown as zero.

## Principles

- **Summary first, detail on request.** Lead with the two or three numbers that answer the
  page's question. Put config, hashes and per-field caveats behind a disclosure.
- **Say a caveat once.** If ten metrics share a basis note, show it once for the group.
- **No internal vocabulary in user copy.** Names like A3, R1, R2, R3 and T05 belong in docs
  and issues, not on the page.
- **Sign and color mean something.** A `+` or green means profit. Costs, drawdown and
  exposure are amounts, not gains.
- **Logic out of the view.** Grouping, deduping and formatting decisions go in `web/src/lib/`
  with Vitest coverage. Components take plain props and render.

## Tasks

Order matters. U1 and U2 are bugs that touch files the later tasks also change, so they land
first.

| ID | Task | Type | Size | Depends on |
|---|---|---|---|---|
| U1 (#53) | Fix currency signs, tones and axis labels | bug | S | none |
| U2 (#54) | Give saved research results their own route | bug | S | none |
| U3 (#55) | Replace the status header with a compact status line | enhancement | S | none |
| U4 (#56) | Show the research catalog as a comparison table | enhancement | M | U2 |
| U5 (#57) | Hide WAIT signals by default and make the threshold visible | enhancement | S | none |
| U6 (#58) | Make the saved result page summary-first | enhancement | M-L | U1, U2 |

### U1: Fix currency signs, tones and axis labels

`formatCurrency` (`web/src/lib/format.ts`) prefixes `+` on every positive number, so the
saved result page shows "+$3,845.09" max drawdown and "+$5,103.17" recorded costs. The
Overview negates drawdown before formatting, so the two pages disagree.

- Split into a signed formatter for P&L-like values and an unsigned one for amounts
  (costs, drawdown, exposure, prices).
- On the saved result page, choose the formatter per metric. The metric's name or unit
  decides, through a lookup in `lib/`, not inline in the page.
- `RMultipleCard`: with no closed trades it shows "+0.00R" in red under Avg loss. Show a
  dash when there is no data, and color by the value's sign, not the field.
- `EquityCurve`: y-axis labels at $100,000 and above are clipped and lose their `$`. Use a
  compact tick formatter (e.g. `$100.3k`) or widen the axis.

### U2: Give saved research results their own route

`/runs/[runId]` serves both local jobs and saved research results; it tries the job store
first and falls back. So opening a result from Research highlights "Run history" in the
side rail.

- Add `/research/[resultId]` for saved results and link to it from the catalog.
- Keep `/runs/[runId]` for jobs. For an ID that isn't a job but is a saved result, redirect
  to the new route so existing links keep working.
- Side rail: `/research/*` highlights Research.

### U3: Replace the status header with a compact status line

`LiveStatus` renders two to four lines of uppercase monospace above every page title
("API refresh does not establish stream health", heartbeat timestamps, runtime detail).

- One line: scope (Live / All sources), API state, heartbeat state as a word
  (fresh / stale / none).
- Full runtime rows and unresolved orders go in a `<details>` disclosure on the same line.
- Keep the `role="alert"` message when the API is unreachable, and always show
  unresolved orders when there are any. Those are the cases that need attention.
- Research: the page shows a scope note and a near-identical warning. Show one.

### U4: Show the research catalog as a comparison table

The catalog is eight tall cards with an empty left half. They are really a grid of
variant by window, and the cards make that comparison impossible.

- One table: variants as rows, windows (development, holdout) as columns, realized net
  P&L in each cell, linking to that saved result.
- Window dates move to the column headers in short form (`Mar 1 – Jul 1, 2026`); the
  inclusive and exclusive wording goes into a header tooltip or footnote.
- Accounting coverage shows once as a footnote when every result shares it, otherwise
  per cell.
- Grouping lives in `lib/` with tests: missing cells, a variant in only one window,
  results flagged synthetic.
- The catalog is paginated. The table groups the current page only. Say so if there is a
  next page.

### U5: Hide WAIT signals by default and make the threshold visible

The Signals page lists every decision with equal weight; most rows are WAIT. Confidence
bars at 66.7% and 71.7% look the same, and the 62% threshold marker is barely visible.

- Add an "Include WAIT" toggle to the filter bar, off by default. Add the criterion to
  `filterSignals` with a test.
- The count line says how many WAIT rows are hidden.
- Make `.meter-threshold` visible against both the filled and empty track.
- Leave the expanded signal view alone; it is the clearest screen in the app.

### U6: Make the saved result page summary-first

The page shows 15 metrics, each with a two-line basis note. It also has five "Unavailable"
cards, metrics repeated between "Saved metrics" and "Accounting audit", and internal
read-model names in the copy.

- Top row: realized net P&L, closed trades, realized max drawdown. Marked values sit
  next to them, labeled as marked.
- Metric groups (realized, marked) each show their basis note once.
- Unavailable cost components collapse to one line: "Not tracked in this result: spread,
  slippage, fees, borrow, dividends", keeping each one's reason available on hover or
  in the disclosure.
- Remove the duplicate metrics from Accounting audit; keep coverage, mode and the
  unresolved list.
- Replace internal names (A3, R1, R2, R3, T05) with plain statements of what isn't
  available yet.
- Configuration, hashes and the artifact inventory move into one collapsed
  "Reproducibility" section.
- Move `METRICS`, the artifact grouping and the basis dedupe out of the page into
  `lib/` with tests.

## Verification for every task

- `cd web && pnpm test` and `pnpm lint` pass.
- Before and after screenshots of the affected pages, attached to the PR. Use the
  synthetic replay plus the indexed research bundle, never `papertrader.db`:

  ```bash
  export DEMO_ROOT="$(mktemp -d)"
  LLM_PROVIDER=template BROKER=local SPREAD_BPS=2 SLIPPAGE_BPS=1 FEE_PER_SHARE=0 \
    .venv/bin/python backtest.py --dataset tests/fixtures/bars.json \
    --db "$DEMO_ROOT/demo.db" --output "$DEMO_ROOT/result"
  PYTHONPATH=. .venv/bin/python -c 'from demo.artifacts import ArtifactIndex; import os; ArtifactIndex(os.environ["DEMO_ROOT"] + "/artifacts.db").import_directory("research-output/alpaca-iex-2026-base-v2", owner_id="local")'
  DB_PATH="$DEMO_ROOT/demo.db" DEMO_ARTIFACT_DB_PATH="$DEMO_ROOT/artifacts.db" \
    LLM_PROVIDER=template BROKER=local .venv/bin/python run_dashboard.py
  ```

  Operational pages need `?source=all`; the fixture is a replay. Headless screenshots can
  catch the equity curve mid-animation, so check charts in a real browser.
- No value that was "Unavailable" before is shown as a number after.

## Out of scope

Visual redesign beyond these screens, new data, backend read models (R1–R3) and the
hosted work in C1–C7.

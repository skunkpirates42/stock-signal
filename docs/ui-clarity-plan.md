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

## Phase 2: design system

The U-tasks fix individual screens. This phase makes the fixes stick. Right now the same
decisions get made per page: three separate ways to render an unavailable value, two
names for the same tone ("neutral" in `StatTile`, "muted" from `toneForSign`), 17
different font sizes, and a `micro` label style that ends up on running text. Each
screen drifts a little, and nothing stops the next one from drifting too.

The goal is a small set of primitives that carry the repo's rules, a page that shows
them, and checks that fail when code goes around them. The test for success: someone who
has never touched the frontend can build a new screen from the primitives and get
unknown-stays-unknown, sign and tone, and spacing right without reading this doc.

### Principles

- **Extract what repeats, nothing else.** Every primitive below has at least three call
  sites today. No speculative components.
- **The invariants live in the primitives.** "Unavailable is never zero" and "sign means
  profit" are enforced by the component and its `lib/` helper, not by each page
  remembering.
- **No new dependencies.** No Storybook, no Tailwind, no stylelint. A `/system` route and
  Vitest checks do the same job for an app this size.
- **Same rules as the rest of the app.** Logic in `lib/` with tests, components props-only.

### Tasks

| ID | Task | Type | Size | Depends on |
|---|---|---|---|---|
| D1 (#66) | Add a type scale and semantic tokens | enhancement | S | none |
| D2 (#67) | One tone vocabulary | enhancement | S | none |
| D3 (#68) | `AvailableValue`: one way to render an observation | enhancement | M | D2 |
| D4 (#69) | `Card`, `Disclosure` and `DataTable` primitives | enhancement | M | D1 |
| D5 (#70) | A `/system` page showing every primitive and its states | enhancement | S | D3, D4 |
| D6 (#71) | Guardrails that fail on drift | enhancement | S | D1, D3 |

D1 and D2 can run in parallel. D3 and D4 touch different files and can too.

### D1: Add a type scale and semantic tokens

`styles/` uses 17 distinct `font-size` values (0.68rem to 1.75rem, several within 0.02rem
of each other). Colors are nearly all tokenized in `tokens.css`; the exceptions are six
background literals in `base.css`. Type and label styles are not tokenized.

- Add a five or six step type scale to `tokens.css` (`--text-label`, `--text-small`,
  `--text-body`, `--text-lead`, `--text-stat`, `--text-title`) and move every `font-size`
  onto it.
- Move the six color literals in `base.css` into tokens.
- Add semantic aliases for the color roles pages actually use: `--positive` and
  `--negative` for P&L, `--caution` for unavailable and warnings. `--win` and `--loss`
  stay as the raw palette.
- Split `.micro` into a label style (uppercase, mono, for short labels) and a note style
  (sentence case, for running text). The research footnotes bug in #56 came from using
  the label style on sentences.

### D2: One tone vocabulary

`toneForSign` returns `positive | negative | muted`; `StatTile` takes
`positive | negative | neutral`. #58 maps one to the other by hand.

- One exported `Tone` type in `lib/format.ts`, used by `toneForSign`, `StatTile`,
  `RMultipleCard` and the comparison table.
- One `tone-*` class per value in CSS.

### D3: `AvailableValue`: one way to render an observation

The "unknown stays unknown" rule is currently enforced three separate times:
`metric()` in `JobDetail.tsx`, `metricValue()` in `lib/savedResult.ts`, and the
"Unavailable" handling in `lib/research-comparison.ts`. They agree today by coincidence.

- `lib/observation.ts`: `describeObservation(name, metric)` returns
  `{ text, tone, reason }`, picking the signed or unsigned formatter through
  `formatMetricAmount`. Tests cover available, unavailable with a reason, missing,
  zero, negative and count units.
- `components/AvailableValue.tsx`: renders the text, the tone class and the reason as a
  `title`. Unavailable values always render the word "Unavailable", never a number.
- Replace the three call sites. Also move the 12 inline `replaceAll("_", " ")` label
  conversions to one `metricLabel` helper.

### D4: `Card`, `Disclosure` and `DataTable` primitives

- `Card`: 18 elements use the `card` surface, 14 of them as
  `<section className="card"><h2>`. A `Card` with an optional title and note replaces
  that pattern.
- `Disclosure`: `StatusLine`, the untracked-costs line and Reproducibility each hand-roll
  `<details>` with different markers and spacing. One component with a summary slot.
- `DataTable`: `VoteTable`, `FillsTable`, `BreakdownTable` and the research comparison
  table each restyle `<table>`. One base table style (header labels, numeric alignment,
  row rules, horizontal scroll on narrow screens) with the four keeping their own columns.

Migrate the existing call sites in the same PR so nothing is left on the old pattern.

### D5: A `/system` page showing every primitive and its states

- A `/system` route, linked from nowhere in the rail, that renders each primitive from
  fixtures: tokens (type scale, colors), `AvailableValue` in every state, `StatTile` in
  each tone, `Card`, `Disclosure` open and closed, and `DataTable` with an empty state.
- Fixtures live next to the page as plain objects. No network calls.
- This is the reference for anyone adding a screen, and the demo for the design-system
  part of the presentation.

### D6: Guardrails that fail on drift

- An ESLint `no-restricted-syntax` rule in `eslint.config.mjs` that flags `.toFixed`,
  `.toLocaleString` and `Intl.*` inside `components/` and `app/`. Formatting goes through
  `lib/format.ts`. The current `RationalePanel` and `FilterBar` hits move to `lib/` first.
- A Vitest check that reads `styles/*.css` and fails on a raw color outside `tokens.css`
  or a `font-size` that isn't a scale token.
- A Vitest check that every primitive renders its unavailable or empty state without a
  number in it.

## Out of scope

Visual redesign beyond these screens, new data, backend read models (R1–R3) and the
hosted work in C1–C7.

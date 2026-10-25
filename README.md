# stock-signal

A rule-based intraday trading signal engine and the dashboard I built to watch it. The
question behind it: can a transparent consensus-of-indicators strategy survive real
trading costs? So far, not convincingly. The results below say so plainly.

**Paper only. No real capital has been traded. This is not investment advice.**

| | |
|---|---|
| **Frontend** | Next.js 16 (App Router, server components), React 19, TypeScript, Recharts, Vitest, ESLint, pnpm |
| **Backend** | Python 3.9, Flask JSON API, SQLite, pandas/numpy, pytest |
| **Data and execution** | Alpaca IEX bars (seeded synthetic fallback, runs fully offline), local fill simulator or Alpaca paper orders |
| **LLM** | Optional, presentation-only signal explanations (Groq or Anthropic). Never touches the trading decision. |
| **Status** | Personal research project, in validation |

## What it does

- Every five minutes, six indicators vote on each ticker. If at least 62% agree, the
  engine emits LONG or SHORT with a stop and a 2:1 target. Otherwise it emits WAIT.
- The decision is a pure, unit-tested function. An LLM can explain a signal on demand but
  can't make or change one.
- Every signal, order and outcome is journaled to SQLite, so the strategy is judged on its
  logged record.
- A replay engine runs the same pipeline over historical bars, with modeled spread and
  slippage, so results are net of costs.

## The dashboard (`web/`)

| Page | What it shows |
|---|---|
| `/` Overview | Net P&L, equity curve, win/loss and R-multiple breakdowns, with source, date-range and extra-cost filters |
| `/signals` | Each signal's votes, confidence against the threshold, price levels and explanation |
| `/positions` | Open positions and fills |
| `/research` | Saved research results, read-only, with their audit artifacts |
| `/run`, `/runs` | Queue a local historical replay on paper, then follow its phases, cancel it or open its results |
| `/system` | The design system: every shared component in each of its states, built from fixtures. Not in the side rail, open it by URL. |

A status line in every page separates "API reachable" from "worker alive and data fresh",
so a stale feed never passes for a healthy one.

## Frontend engineering

**Logic lives outside the components.** Data fetching, transforms, metrics and formatting
live in `web/src/lib/`, with tests alongside. Components take plain props and
render markup. ESLint fails any inline `toFixed` or `Intl` call in a view, so numbers are
always formatted through `lib/format.ts`.

**The design system is enforced by tests, not by convention.**

- `styles/tokens.css` holds the colors, type scale, spacing unit and radii.
  `styles.test.ts` fails if a stylesheet uses a color, font size, spacing value or radius
  that isn't a token.
- `conventions.test.ts` fails if a page writes its own `<main>`, page header or scope
  note instead of going through `Page`, `PageHeader` or `ScopeNote`.
- Missing data is never shown as zero. `AvailableValue` renders the reason a value is
  unavailable, and `primitives.test.ts` checks that empty states never render a number.

**Accessibility**

- Text color tokens are tested against WCAG AA contrast on the page background.
- A skip link jumps past the side rail to the page's `<main>` landmark.
- The equity curve has a text summary for screen readers, and the confidence meter
  announces the threshold it's measured against.
- Unavailable reasons are visible text, not hover-only tooltips.
- Animations respect `prefers-reduced-motion`.

## Architecture

| Area | Path | What it does |
|---|---|---|
| Signal engine | `signals/` | Six indicator votes plus a volume modifier. A consensus threshold decides direction. |
| Market data | `data/` | Alpaca IEX bars, REST for history and websocket for live, aggregated to five minutes. |
| Execution | `trades/` | Local fill simulator by default. Alpaca paper orders with `BROKER=alpaca` (hardcoded `paper=True`). Restart-safe. |
| Replay | `backtest.py`, `research.py` | Replays bars chronologically through the same pipeline as live, and compares research gates across fixed windows. |
| API | `dashboard/` | Flask JSON API for the dashboard, plus the saved-research and run-queue endpoints. |
| Research and runs | `demo/` | Read-only index of saved research bundles, a run queue in its own SQLite file, and a single worker that runs replays in an isolated subprocess and verifies output before publishing. |
| Persistence | `db/` | SQLite journal of signals, trades, run manifests and orders. |
| Dashboard | `web/` | The Next.js app above. |

## Running it

Everything below runs offline, with no API keys.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

# Replay the bundled synthetic fixture into a local database
.venv/bin/python backtest.py --dataset tests/fixtures/bars.json --db fixture.db --output fixture-report

# API on http://127.0.0.1:8000
DB_PATH=fixture.db .venv/bin/python run_dashboard.py
```

In a second terminal:

```bash
cd web
pnpm install
pnpm dev    # http://localhost:3000
```

The Overview starts on live trades only. Switch **Scope** to **All** to see the fixture's
backtest trades.

To run replays from the `/run` page, start the worker in a third terminal:

```bash
DB_PATH=fixture.db .venv/bin/python -m demo.worker
```

For live Alpaca data or LLM explanations, copy `.env.example` to `.env` and fill in keys.
`FLASK_API_URL` points the web app at an API that isn't on port 8000.

Tests and checks:

```bash
.venv/bin/python -m pytest tests/ -q          # backend
cd web && pnpm test && pnpm lint && pnpm build  # frontend
```

The fixture checks plumbing, not strategy. The saved research bundles and real market bars
are local and gitignored, so a fresh clone can't reproduce the figures below. The
[read-model contract](docs/engine-demo/README.md) covers importing a saved bundle into the
Research pages.

## Results so far

A January–August 2026 Alpaca IEX experiment compared the unchanged baseline with three
quality gates. Development covered 84 March–June sessions, and the holdout covered 43
July–August sessions. "Adverse" reruns the holdout with higher modeled costs.

| Marked net P&L | Development | Holdout | Holdout, adverse costs |
| --- | ---: | ---: | ---: |
| Baseline | +$2,226.27 | +$412.68 | −$5,718.88 |
| Relative strength | +$3,855.20 | −$902.36 | −$5,311.27 |
| RVOL | −$970.92 | +$3,460.79 | −$105.35 |
| Both gates | +$1,490.52 | +$76.77 | −$2,490.78 |

**No variant was promoted.** RVOL had the best holdout but lost in development, went
slightly negative under adverse costs, and its paired uncertainty interval against
baseline crossed zero. The holdout has now been viewed, so it can't validate a revised
strategy.

Base costs are 2 bps round-trip spread and 1 bp slippage per fill. Adverse costs are 5 bps
and 2 bps. These are declared assumptions, not measured execution costs. Marked results
value open positions at the latest completed close. Dividends, short borrow and actual
quote spreads aren't fully accounted for. Next steps: complete cash-flow accounting,
evidence for execution costs, and forward observation of baseline against RVOL.

Execution rules, the research workflow and older archived findings (unverified, from a
replay with known defects) are in [docs/research-notes.md](docs/research-notes.md).

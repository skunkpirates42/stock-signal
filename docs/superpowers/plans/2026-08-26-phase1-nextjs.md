# Phase 1 — Next.js Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Next.js App Router dashboard that replaces the Flask UI and surfaces, for every signal, the reasoning text and the six indicator votes behind the decision — the thing the current UI shows nowhere.

**Architecture:** Server components fetch the Flask API on localhost and pass plain typed props to presentational components. All domain logic (parsing, filtering, formatting) lives in `web/src/lib/` as pure functions testable without a DOM. Client components exist only where interaction demands: the Recharts equity curve, the signal filter bar, and expandable rationale panels.

**Tech Stack:** Next.js (App Router), TypeScript, pnpm, Recharts, Vitest. No UI component library.

**Spec:** `docs/superpowers/specs/2026-08-26-nextjs-dashboard-design.md`

## Branch

Phase 1 depends on the `?source=` query parameters delivered in Phase 0, which live on `nextjs-dashboard` (PR #1, open, unmerged). **Branch from `nextjs-dashboard`, not `main`:**

```bash
git checkout nextjs-dashboard && git pull && git checkout -b nextjs-frontend
```

## Global Constraints

- **pnpm only.** Not npm, not yarn. Node v25.9.0, pnpm 10.33.0 are installed.
- **TypeScript throughout.** No `.js` source files. No `any` — use `unknown` and narrow.
- **App Router only.** No `pages/` directory. This is a deliberate learning goal.
- **No UI component library.** No MUI, Chakra, shadcn, Tailwind plugins beyond Tailwind itself if used. Recharts and Vitest are the only new runtime/dev dependencies authorized.
- **Business logic never lives in a component.** No `fetch`, no data reshaping, no domain rules inside JSX. Components take plain props and render.
- **Every `lib/` function must be testable without mounting a component or a DOM.**
- **The Python backend is not modified in this phase.** If something is missing from the API, report it rather than editing Flask.
- **Never commit on `main`.** Never push without being asked.
- **The Flask API must be running** for pages to render: `source .venv/bin/activate && python3 run_dashboard.py` (port 8000).

## Verified API contract

Captured from the live API on 2026-08-26. Types below are derived from real responses, not guessed.

`GET /api/metrics?source=live` returns a flat object:

```
n_closed 15 | n_open 5 | n_wins 3 | n_losses 12
win_rate 0.2                    <- FRACTION, not percent
avg_win 51.05 | avg_loss -31.25
expectancy -14.79
profit_factor 0.408             <- null when there are no losses
total_pnl -221.89
max_drawdown 269.8
max_drawdown_pct 0.002698...    <- FRACTION, needs rounding
avg_bars_held 10.1
avg_r_multiple -0.4 | avg_win_r 2.0 | avg_loss_r -1.0
starting_capital 100000.0 | ending_capital 99778.11
by_ticker  {"AAPL": {n: 3, wins: 1, win_rate: 0.333..., pnl: -13.31}, ...}
by_regime  {"BEAR": {n: 2, wins: 0, win_rate: 0.0, pnl: -45.64}, ...}
equity     [{label: "start"|"2026-07-15T17:11:00", equity: 99967.96, pnl: -32.04}, ...]
```

`GET /api/signals?source=live&limit=500` returns an array of:

```
id 404 | ticker "MSFT" | direction "WAIT"|"LONG"|"SHORT"
confidence 0.55                 <- FRACTION
entry 395.61
stop, target, rr                <- ALL null when direction is WAIT
bar_timestamp "2026-07-15 19:55:00+00:00"   <- space separator, not ISO T
created_at "2026-07-15T20:54:00.144301+00:00"
regime "BULL" | source "live"
synthesis_source "groq:qwen/qwen3.6-27b" | "template"
reasoning "The engine decided to wait due to..."
indicators_json  <- a JSON *string* that must be parsed; see below
```

Parsed `indicators_json` has exactly three keys:

```json
{
  "votes":  {"rsi":"neutral","price_vs_sma20":"bear","sma20_vs_sma50":"bear",
             "price_vs_vwap":"bull","macd":"bear","bb":"neutral"},
  "values": {"close":395.61,"rsi":49.05,"sma20":395.87,"sma50":396.13,"vwap":392.95,
             "macd":-0.205,"bb_pct":0.393,"volume_ratio":2.637,"atr":0.745},
  "tally":  {"bull":1,"bear":3,"neutral":2}
}
```

Other endpoints: `GET /api/trades?source=&limit=`, `GET /api/open` (no source filter — all open trades are live), `GET /api/alerts`.

## File Structure

| File | Responsibility |
|---|---|
| `web/src/lib/types.ts` | `Signal`, `Trade`, `Metrics`, `Breakdown`, `EquityPoint`, `VoteRow`, `Vote` |
| `web/src/lib/api.ts` | Typed fetch against Flask — the ONLY place I/O happens |
| `web/src/lib/format.ts` | currency, percent, R-multiple, timestamp |
| `web/src/lib/indicators.ts` | `parseIndicators` — JSON string → `VoteRow[]` |
| `web/src/lib/filters.ts` | `filterSignals` predicates |
| `web/src/lib/costs.ts` | gross → net expectancy |
| `web/src/app/page.tsx` | Overview (server) |
| `web/src/app/signals/page.tsx` | Signal history (server shell) |
| `web/src/app/positions/page.tsx` | Open positions + fills (server) |
| `web/src/components/*` | Presentational, plain props |

---

### Task 1: Scaffold and the typed API seam

**Files:**
- Create: `web/` (Next.js app), `web/src/lib/types.ts`, `web/src/lib/api.ts`, `web/src/lib/format.ts`
- Test: `web/src/lib/format.test.ts`

**Interfaces:**
- Consumes: nothing
- Produces: every type in `types.ts`; `getMetrics(source?)`, `getSignals(opts)`, `getTrades(opts)`, `getOpenPositions()` from `api.ts`; `formatCurrency`, `formatPercent`, `formatR`, `formatTimestamp` from `format.ts`

- [ ] **Step 1: Scaffold**

```bash
cd /Users/peterr/Desktop/stock-signal
pnpm create next-app@latest web --ts --app --src-dir --eslint --no-tailwind --import-alias "@/*" --use-pnpm
cd web && pnpm add recharts && pnpm add -D vitest
```

If `create-next-app` prompts interactively despite the flags, accept: TypeScript yes, ESLint yes, Tailwind no, `src/` yes, App Router yes, Turbopack default, import alias `@/*`.

- [ ] **Step 2: Add the test script and Vitest config**

`web/package.json` — add to `scripts`: `"test": "vitest run"`.

Create `web/vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  test: { environment: "node", include: ["src/**/*.test.ts"] },
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
});
```

`environment: "node"` is deliberate — every `lib/` function must be testable without a DOM.

- [ ] **Step 3: Write the types**

Create `web/src/lib/types.ts`:

```ts
export type Direction = "LONG" | "SHORT" | "WAIT";
export type Vote = "bull" | "bear" | "neutral";
export type Source = "live" | "backtest" | "poc";

export interface Signal {
  id: number;
  ticker: string;
  direction: Direction;
  confidence: number;
  entry: number | null;
  stop: number | null;
  target: number | null;
  rr: number | null;
  bar_timestamp: string | null;
  created_at: string;
  regime: string | null;
  source: Source | null;
  synthesis_source: string | null;
  reasoning: string | null;
  indicators_json: string | null;
}

export interface Trade {
  id: number;
  signal_id: number | null;
  ticker: string;
  direction: Direction;
  entry: number;
  stop: number;
  target: number;
  shares: number;
  exit_price: number | null;
  outcome: "OPEN" | "WIN" | "LOSS";
  pnl: number | null;
  entry_bar: number | null;
  exit_bar: number | null;
  bars_held: number | null;
  created_at: string;
  closed_at: string | null;
  source: Source | null;
}

export interface Breakdown {
  n: number;
  wins: number;
  win_rate: number;
  pnl: number;
}

export interface EquityPoint {
  label: string;
  equity: number;
  pnl: number;
}

export interface Metrics {
  n_closed: number;
  n_open: number;
  n_wins: number;
  n_losses: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  expectancy: number;
  profit_factor: number | null;
  total_pnl: number;
  max_drawdown: number;
  max_drawdown_pct: number;
  avg_bars_held: number;
  avg_r_multiple: number;
  avg_win_r: number;
  avg_loss_r: number;
  by_ticker: Record<string, Breakdown>;
  by_regime: Record<string, Breakdown>;
  starting_capital: number;
  ending_capital: number;
  equity: EquityPoint[];
}

export interface VoteRow {
  indicator: string;
  label: string;
  vote: Vote;
  detail: string;
}
```

- [ ] **Step 4: Write the API seam**

Create `web/src/lib/api.ts`:

```ts
import type { Metrics, Signal, Trade } from "@/lib/types";

const BASE = process.env.FLASK_API_URL ?? "http://127.0.0.1:8000";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${path} responded ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getMetrics(source?: string) {
  const query = source ? `?source=${source}` : "";
  return get<Metrics>(`/api/metrics${query}`);
}

export function getSignals(opts: { source?: string; limit?: number } = {}) {
  const params = new URLSearchParams();
  if (opts.source) params.set("source", opts.source);
  params.set("limit", String(opts.limit ?? 500));
  return get<Signal[]>(`/api/signals?${params}`);
}

export function getTrades(opts: { source?: string; limit?: number } = {}) {
  const params = new URLSearchParams();
  if (opts.source) params.set("source", opts.source);
  params.set("limit", String(opts.limit ?? 500));
  return get<Trade[]>(`/api/trades?${params}`);
}

export function getOpenPositions() {
  return get<Trade[]>("/api/open");
}
```

This is the only module that performs I/O. Moving to a committed snapshot or hosted Postgres later changes this file and nothing else.

- [ ] **Step 5: Write the failing formatter tests**

Create `web/src/lib/format.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { formatCurrency, formatPercent, formatR, formatTimestamp } from "@/lib/format";

describe("formatCurrency", () => {
  it("signs positive values", () => expect(formatCurrency(51.05)).toBe("+$51.05"));
  it("signs negative values", () => expect(formatCurrency(-31.25)).toBe("-$31.25"));
  it("renders zero unsigned", () => expect(formatCurrency(0)).toBe("$0.00"));
  it("groups thousands", () => expect(formatCurrency(99778.11)).toBe("+$99,778.11"));
  it("renders null as a dash", () => expect(formatCurrency(null)).toBe("—"));
});

describe("formatPercent", () => {
  it("converts a fraction", () => expect(formatPercent(0.2)).toBe("20.0%"));
  it("rounds a long fraction", () => expect(formatPercent(0.002698)).toBe("0.3%"));
  it("renders null as a dash", () => expect(formatPercent(null)).toBe("—"));
});

describe("formatR", () => {
  it("signs and suffixes", () => expect(formatR(-0.4)).toBe("-0.40R"));
  it("signs positives", () => expect(formatR(2)).toBe("+2.00R"));
});

describe("formatTimestamp", () => {
  it("handles the space-separated bar_timestamp form", () => {
    expect(formatTimestamp("2026-07-15 19:55:00+00:00")).toBe("2026-07-15 19:55");
  });
  it("handles the ISO created_at form", () => {
    expect(formatTimestamp("2026-07-15T20:54:00.144301+00:00")).toBe("2026-07-15 20:54");
  });
  it("passes through the literal start label", () => {
    expect(formatTimestamp("start")).toBe("start");
  });
  it("renders null as a dash", () => expect(formatTimestamp(null)).toBe("—"));
});
```

- [ ] **Step 6: Run them to verify they fail**

```bash
cd web && pnpm test
```

Expected: failures — cannot resolve `@/lib/format`.

- [ ] **Step 7: Implement the formatters**

Create `web/src/lib/format.ts`:

```ts
const DASH = "—";

export function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  const abs = Math.abs(value).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (value === 0) return `$${abs}`;
  return `${value > 0 ? "+" : "-"}$${abs}`;
}

export function formatPercent(fraction: number | null | undefined): string {
  if (fraction === null || fraction === undefined) return DASH;
  return `${(fraction * 100).toFixed(1)}%`;
}

export function formatR(value: number | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  return `${value >= 0 ? "+" : "-"}${Math.abs(value).toFixed(2)}R`;
}

export function formatTimestamp(raw: string | null | undefined): string {
  if (!raw) return DASH;
  if (raw === "start") return raw;
  return raw.replace("T", " ").slice(0, 16);
}
```

`formatTimestamp` deliberately does not construct a `Date`. The stored strings are already UTC wall-clock values from the engine; parsing and re-rendering them would shift every timestamp by the viewer's offset and silently misreport when a signal fired.

- [ ] **Step 8: Run the tests**

```bash
cd web && pnpm test
```

Expected: all format tests pass.

- [ ] **Step 9: Verify the build and the API seam against the real backend**

In one terminal: `source .venv/bin/activate && python3 run_dashboard.py`

Then:

```bash
cd web && pnpm build
node -e "fetch('http://127.0.0.1:8000/api/metrics?source=live').then(r=>r.json()).then(m=>console.log('n_closed',m.n_closed,'expectancy',m.expectancy))"
```

Expected: build succeeds; the node check prints `n_closed 15 expectancy -14.79`.

- [ ] **Step 10: Commit**

```bash
git add web/
git commit -m "Scaffold Next.js app with typed API seam and formatters"
```

---

### Task 2: Domain logic — indicator parsing and filters

**Files:**
- Create: `web/src/lib/indicators.ts`, `web/src/lib/filters.ts`, `web/src/lib/costs.ts`
- Test: `web/src/lib/indicators.test.ts`, `web/src/lib/filters.test.ts`, `web/src/lib/costs.test.ts`

**Interfaces:**
- Consumes: `Signal`, `VoteRow`, `Vote` from `types.ts`
- Produces: `parseIndicators(json: string | null): VoteRow[]`, `voteTally(rows: VoteRow[])`, `filterSignals(signals, criteria): Signal[]`, `netExpectancy(gross, costPerTrade): number`

- [ ] **Step 1: Write the failing tests**

Create `web/src/lib/indicators.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { parseIndicators, voteTally } from "@/lib/indicators";

const REAL = JSON.stringify({
  votes: { rsi: "neutral", price_vs_sma20: "bear", sma20_vs_sma50: "bear",
           price_vs_vwap: "bull", macd: "bear", bb: "neutral" },
  values: { close: 395.61, rsi: 49.05, sma20: 395.87, sma50: 396.13, vwap: 392.95,
            macd: -0.205, bb_pct: 0.393, volume_ratio: 2.637, atr: 0.745 },
  tally: { bull: 1, bear: 3, neutral: 2 },
});

describe("parseIndicators", () => {
  it("returns all six indicators in display order", () => {
    const rows = parseIndicators(REAL);
    expect(rows.map((r) => r.indicator)).toEqual([
      "rsi", "price_vs_sma20", "sma20_vs_sma50", "price_vs_vwap", "macd", "bb",
    ]);
  });

  it("carries each vote through", () => {
    const rows = parseIndicators(REAL);
    expect(rows.find((r) => r.indicator === "macd")?.vote).toBe("bear");
    expect(rows.find((r) => r.indicator === "price_vs_vwap")?.vote).toBe("bull");
  });

  it("gives every row a human label", () => {
    expect(parseIndicators(REAL).find((r) => r.indicator === "bb")?.label)
      .toBe("BB %B");
  });

  it("shows the value that produced the vote", () => {
    const rows = parseIndicators(REAL);
    expect(rows.find((r) => r.indicator === "rsi")?.detail).toContain("49.05");
    expect(rows.find((r) => r.indicator === "price_vs_sma20")?.detail).toContain("395.61");
  });

  it("returns empty for null rather than throwing", () => {
    expect(parseIndicators(null)).toEqual([]);
  });

  it("returns empty for malformed JSON rather than throwing", () => {
    expect(parseIndicators("{not json")).toEqual([]);
  });

  it("returns empty when the votes key is missing", () => {
    expect(parseIndicators(JSON.stringify({ values: {} }))).toEqual([]);
  });
});

describe("voteTally", () => {
  it("counts each side", () => {
    expect(voteTally(parseIndicators(REAL))).toEqual({ bull: 1, bear: 3, neutral: 2 });
  });

  it("handles an empty list", () => {
    expect(voteTally([])).toEqual({ bull: 0, bear: 0, neutral: 0 });
  });
});
```

Create `web/src/lib/filters.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { filterSignals } from "@/lib/filters";
import type { Signal } from "@/lib/types";

function signal(over: Partial<Signal>): Signal {
  return {
    id: 1, ticker: "AAPL", direction: "LONG", confidence: 0.7,
    entry: 100, stop: 98, target: 104, rr: 2,
    bar_timestamp: "2026-07-15 19:55:00+00:00",
    created_at: "2026-07-15T20:00:00+00:00",
    regime: "BULL", source: "live",
    synthesis_source: "groq:qwen/qwen3.6-27b",
    reasoning: "x", indicators_json: "{}",
    ...over,
  };
}

describe("filterSignals", () => {
  const all = [
    signal({ id: 1, ticker: "AAPL", direction: "LONG", confidence: 0.7 }),
    signal({ id: 2, ticker: "NVDA", direction: "SHORT", confidence: 0.9 }),
    signal({ id: 3, ticker: "AAPL", direction: "WAIT", confidence: 0.55 }),
  ];

  it("returns everything with empty criteria", () => {
    expect(filterSignals(all, {})).toHaveLength(3);
  });

  it("filters by ticker", () => {
    expect(filterSignals(all, { ticker: "AAPL" }).map((s) => s.id)).toEqual([1, 3]);
  });

  it("filters by direction", () => {
    expect(filterSignals(all, { direction: "SHORT" }).map((s) => s.id)).toEqual([2]);
  });

  it("filters by minimum confidence inclusively", () => {
    expect(filterSignals(all, { minConfidence: 0.7 }).map((s) => s.id)).toEqual([1, 2]);
  });

  it("filters by date range on bar_timestamp", () => {
    const older = signal({ id: 4, bar_timestamp: "2026-06-01 10:00:00+00:00" });
    const result = filterSignals([...all, older], { from: "2026-07-01" });
    expect(result.map((s) => s.id)).toEqual([1, 2, 3]);
  });

  it("combines criteria", () => {
    expect(filterSignals(all, { ticker: "AAPL", direction: "LONG" }).map((s) => s.id))
      .toEqual([1]);
  });

  it("returns empty when nothing matches", () => {
    expect(filterSignals(all, { ticker: "TSLA" })).toEqual([]);
  });
});
```

Create `web/src/lib/costs.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { netExpectancy } from "@/lib/costs";

describe("netExpectancy", () => {
  it("subtracts the round-trip cost from a positive edge", () => {
    expect(netExpectancy(3, 2)).toBe(1);
  });

  it("drives a thin edge negative", () => {
    expect(netExpectancy(3, 3.5)).toBeCloseTo(-0.5);
  });

  it("makes a negative edge worse", () => {
    expect(netExpectancy(-14.79, 2)).toBeCloseTo(-16.79);
  });

  it("returns gross when the cost is zero", () => {
    expect(netExpectancy(-14.79, 0)).toBe(-14.79);
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd web && pnpm test
```

Expected: failures — cannot resolve `@/lib/indicators`, `@/lib/filters`, `@/lib/costs`.

- [ ] **Step 3: Implement `indicators.ts`**

```ts
import type { Vote, VoteRow } from "@/lib/types";

const ORDER = [
  "rsi", "price_vs_sma20", "sma20_vs_sma50", "price_vs_vwap", "macd", "bb",
] as const;

const LABELS: Record<string, string> = {
  rsi: "RSI (14)",
  price_vs_sma20: "Price vs SMA20",
  sma20_vs_sma50: "SMA20 vs SMA50",
  price_vs_vwap: "Price vs VWAP",
  macd: "MACD",
  bb: "BB %B",
};

function detailFor(indicator: string, values: Record<string, number>): string {
  const n = (key: string, digits = 2) =>
    values[key] === undefined ? "—" : values[key].toFixed(digits);
  switch (indicator) {
    case "rsi": return `${n("rsi")}  (bull <45, bear >55)`;
    case "price_vs_sma20": return `${n("close")} vs ${n("sma20")}`;
    case "sma20_vs_sma50": return `${n("sma20")} vs ${n("sma50")}`;
    case "price_vs_vwap": return `${n("close")} vs ${n("vwap")}`;
    case "macd": return n("macd", 3);
    case "bb": return `${n("bb_pct", 3)}  (bull <0.20, bear >0.80)`;
    default: return "";
  }
}

export function parseIndicators(json: string | null | undefined): VoteRow[] {
  if (!json) return [];
  let parsed: { votes?: Record<string, Vote>; values?: Record<string, number> };
  try {
    parsed = JSON.parse(json);
  } catch {
    return [];
  }
  const votes = parsed.votes;
  if (!votes) return [];
  const values = parsed.values ?? {};
  return ORDER.filter((key) => key in votes).map((key) => ({
    indicator: key,
    label: LABELS[key] ?? key,
    vote: votes[key],
    detail: detailFor(key, values),
  }));
}

export function voteTally(rows: VoteRow[]) {
  return {
    bull: rows.filter((r) => r.vote === "bull").length,
    bear: rows.filter((r) => r.vote === "bear").length,
    neutral: rows.filter((r) => r.vote === "neutral").length,
  };
}
```

`voteTally` recounts from the parsed rows rather than reading the stored `tally` key, so the displayed count can never disagree with the displayed rows.

- [ ] **Step 4: Implement `filters.ts`**

```ts
import type { Direction, Signal } from "@/lib/types";

export interface SignalCriteria {
  ticker?: string;
  direction?: Direction;
  minConfidence?: number;
  from?: string;
  to?: string;
}

export function filterSignals(signals: Signal[], criteria: SignalCriteria): Signal[] {
  return signals.filter((s) => {
    if (criteria.ticker && s.ticker !== criteria.ticker) return false;
    if (criteria.direction && s.direction !== criteria.direction) return false;
    if (criteria.minConfidence !== undefined && s.confidence < criteria.minConfidence) {
      return false;
    }
    const day = (s.bar_timestamp ?? s.created_at).slice(0, 10);
    if (criteria.from && day < criteria.from) return false;
    if (criteria.to && day > criteria.to) return false;
    return true;
  });
}
```

Date comparison is lexicographic on the `YYYY-MM-DD` prefix — correct for ISO dates and avoids timezone-shifting the stored UTC wall-clock values.

- [ ] **Step 5: Implement `costs.ts`**

```ts
export const DEFAULT_COST_PER_TRADE = 2.0;

export function netExpectancy(grossExpectancy: number, costPerTrade: number): number {
  return grossExpectancy - costPerTrade;
}
```

The default reflects the $1.50–3.00 per-trade friction range documented in `README.md`.

- [ ] **Step 6: Run the tests**

```bash
cd web && pnpm test
```

Expected: all indicator, filter, cost, and format tests pass.

- [ ] **Step 7: Commit**

```bash
git add web/src/lib
git commit -m "Add indicator parsing, signal filters, and cost adjustment"
```

---

### Task 3: Overview page

**Files:**
- Modify: `web/src/app/page.tsx`, `web/src/app/layout.tsx`, `web/src/app/globals.css`
- Create: `web/src/components/StatTile.tsx`, `web/src/components/ProvenanceBand.tsx`, `web/src/components/BreakdownTable.tsx`, `web/src/components/CostAdjustedExpectancy.tsx`, `web/src/components/Nav.tsx`

**Interfaces:**
- Consumes: `getMetrics` from `api.ts`; `formatCurrency`/`formatPercent` from `format.ts`; `netExpectancy`/`DEFAULT_COST_PER_TRADE` from `costs.ts`
- Produces: `StatTile`, `BreakdownTable`, `ProvenanceBand`, `Nav` for reuse on later pages

- [ ] **Step 1: Build the layout shell and nav**

`web/src/app/layout.tsx` renders `<Nav />` above `{children}`. `Nav` is a server component with three links: `/` (Overview), `/signals` (Signals), `/positions` (Positions).

Put a dark theme in `globals.css` using CSS custom properties. Match the existing Flask palette so the two dashboards are visually continuous: `--bg:#0f1419; --panel:#1a2029; --line:#2a323d; --fg:#e6e9ee; --muted:#8a94a3; --green:#3fb950; --red:#f85149; --accent:#58a6ff`.

- [ ] **Step 2: Build `StatTile`**

Presentational only. Props: `{ label: string; value: string; tone?: "positive" | "negative" | "neutral"; note?: string }`. Renders a bordered panel with the label small and muted above the value. No logic — the caller decides the tone and passes a pre-formatted string.

- [ ] **Step 3: Build `ProvenanceBand`**

Props: `{ source: "live" | "all"; nClosed: number }`.

It must state, in words, which rows the numbers cover — "Showing 15 live trades. Backtest rows excluded." — and link to `/?source=all` to include them (and back). This is a server component; the toggle is a link, not client state, so the server refetches with the right filter.

When `nClosed < 50` it must also render a provisional warning: fewer than 50 closed trades is below the evaluation floor in `CLAUDE.md` and no conclusion should be drawn.

- [ ] **Step 4: Build `CostAdjustedExpectancy`**

`"use client"` — it owns a cost input. Props: `{ grossExpectancy: number }`.

Renders gross and net side by side with a number input for cost per trade, defaulting to `DEFAULT_COST_PER_TRADE`. Net is computed with `netExpectancy` from `lib/costs.ts` — the arithmetic does not live in the component.

The point is honesty: `README.md` concluded the edge sits below realistic transaction costs, so showing gross alone would mislead.

- [ ] **Step 5: Build `BreakdownTable`**

Props: `{ title: string; rows: Record<string, Breakdown> }`. Renders name / N / win% / P&L, sorted by P&L descending. Used twice — by ticker and by regime.

- [ ] **Step 6: Wire the page**

`web/src/app/page.tsx` is an async server component:

```tsx
export default async function OverviewPage({
  searchParams,
}: {
  searchParams: Promise<{ source?: string }>;
}) {
  const { source } = await searchParams;
  const scope = source === "all" ? undefined : "live";
  const metrics = await getMetrics(scope);
  // ...render
}
```

`searchParams` is a Promise in current App Router versions and must be awaited. If the installed Next.js version types it as a plain object, drop the `await` and the `Promise<>` wrapper — follow what the types say.

Render order: `ProvenanceBand` → stat tiles (win rate, expectancy, total P&L, max drawdown, closed, open) → `CostAdjustedExpectancy` → `BreakdownTable` by regime → `BreakdownTable` by ticker. The equity curve slot stays empty until Task 4.

- [ ] **Step 7: Verify against the real backend**

With Flask running, `cd web && pnpm dev`, then load `http://localhost:3000`.

Confirm by reading the page: win rate 20.0%, expectancy −$14.79, total P&L −$221.89, 15 closed / 5 open, the provisional warning is visible (15 < 50), and `?source=all` changes the numbers to the blended set (150 closed, −$0.72).

- [ ] **Step 8: Build and commit**

```bash
cd web && pnpm test && pnpm build
git add web/
git commit -m "Add overview page with provenance and cost-adjusted expectancy"
```

---

### Task 4: Equity curve

**Files:**
- Create: `web/src/components/EquityCurve.tsx`
- Modify: `web/src/app/page.tsx`

**Interfaces:**
- Consumes: `EquityPoint[]` from `types.ts`, `formatCurrency`, `formatTimestamp`
- Produces: `EquityCurve` component

- [ ] **Step 1: Build the chart**

`web/src/components/EquityCurve.tsx` starts with `"use client"` — Recharts measures the DOM and cannot render on the server.

Props: `{ points: EquityPoint[] }`. Nothing else. It receives data already shaped by the server and does no fetching, no filtering, and no derivation beyond what Recharts needs for axes.

Use `ResponsiveContainer` + `LineChart` + `Line` (`type="monotone"`, `dot={false}`) + `XAxis` (`tickFormatter={formatTimestamp}`) + `YAxis` (`domain={["auto", "auto"]}`, `tickFormatter` to currency) + `Tooltip` + `CartesianGrid`. Colors come from the CSS custom properties defined in Task 3.

Give `ResponsiveContainer` an explicit pixel height (e.g. 260) — it collapses to zero inside a flex parent without one.

- [ ] **Step 2: Handle the empty case**

With fewer than two points there is no line to draw. Render "Not enough closed trades to plot" rather than an empty axis frame. `?source=live` currently yields 16 points, so exercise this path by checking `points.length < 2` explicitly.

- [ ] **Step 3: Mount it**

Add `<EquityCurve points={metrics.equity} />` to `page.tsx` in the slot left in Task 3. The server component passes a plain array across the boundary — no functions, no class instances, since only serializable props cross into a client component.

- [ ] **Step 4: Verify**

With Flask and `pnpm dev` running, load `http://localhost:3000` and confirm: the curve renders, starts at 100,000, ends at 99,778.11, and has 16 points under `?source=live`. Switch to `?source=all` and confirm it redraws with the blended 151-point series.

Then confirm no hydration error appears in the browser console. A hydration mismatch here means something non-deterministic leaked into render.

- [ ] **Step 5: Build and commit**

```bash
cd web && pnpm test && pnpm build
git add web/
git commit -m "Add Recharts equity curve"
```

---

### Task 5: Signals page with rationale panel

This is the centerpiece — the view that shows what the Flask dashboard shows nowhere.

**Files:**
- Modify: `web/src/app/signals/page.tsx`
- Create: `web/src/components/SignalList.tsx`, `web/src/components/SignalRow.tsx`, `web/src/components/RationalePanel.tsx`, `web/src/components/VoteTable.tsx`, `web/src/components/FilterBar.tsx`

**Interfaces:**
- Consumes: `getSignals`, `filterSignals`, `parseIndicators`, `voteTally`, formatters
- Produces: nothing later tasks depend on

- [ ] **Step 1: Fetch on the server**

`web/src/app/signals/page.tsx` is an async server component that calls `getSignals({ source: "live", limit: 500 })` and passes the array to `<SignalList signals={signals} />`.

269 rows is small enough to filter in the browser after one fetch. **Add a comment at the call site stating that this stops being appropriate somewhere around a few thousand rows, at which point the predicates move into the Flask query.** Naming the limit is the point.

- [ ] **Step 2: Build `FilterBar` and `SignalList`**

`SignalList` is `"use client"` and owns the filter state. It renders `<FilterBar>` and the filtered rows, calling `filterSignals` from `lib/` — the predicates are not reimplemented inline.

`FilterBar` props: current criteria plus an `onChange` callback. Controls: ticker (a select built from the distinct tickers present), direction (LONG / SHORT / WAIT / any), min confidence (a range input), and from/to dates.

Show the result count against the total — "showing 42 of 269" — so a filter returning nothing is legible rather than looking broken.

- [ ] **Step 3: Build `SignalRow`**

One collapsed line: ticker, a direction badge, confidence, timestamp, and — when the signal produced a trade — its outcome. Clicking toggles the rationale panel. Track expansion by signal `id`.

Colour direction by the same palette as the Flask UI: LONG/WIN green, SHORT/LOSS red, WAIT muted.

- [ ] **Step 4: Build `VoteTable`**

Props: `{ rows: VoteRow[] }`. Renders indicator label, vote, and detail for all six, colour-coded. Pure presentation over what `parseIndicators` produced.

Render nothing but a short muted note if `rows` is empty — a malformed `indicators_json` must not blank the whole panel.

- [ ] **Step 5: Build `RationalePanel`**

Props: `{ signal: Signal }`. This is the payoff, so its layout carries weight. It renders:

1. **The reasoning text**, with its provenance label. `synthesis_source` must be shown as-is — `groq:qwen/qwen3.6-27b` or `template` — never relabelled or hidden. If it is null, say "provenance not recorded" rather than implying a model wrote it.
2. **The vote table**, headed by the tally from `voteTally`.
3. **The levels** — entry, stop, target, R:R — when the direction is not WAIT. `stop`, `target`, and `rr` are null on WAIT rows; render a short line explaining the engine stood aside instead of showing empty fields.

- [ ] **Step 6: Verify against real data**

With both servers running, load `http://localhost:3000/signals` and confirm:

- 269 rows load
- A WAIT row expands to show all six votes and no level fields
- A LONG or SHORT row shows entry/stop/target/R:R
- Rows backfilled through Groq are labelled `groq:qwen/qwen3.6-27b`; the 111 older rows are labelled `template`
- Filtering by ticker AAPL narrows the count and the header reflects it
- Setting min confidence to 0.62 excludes the WAIT rows at 0.55

Pick one expanded row and check its vote table against the database directly:

```bash
sqlite3 -line papertrader.db "select ticker, direction, indicators_json from signals where id = <the id you expanded>;"
```

The six votes on screen must match the stored JSON exactly. This is the check that catches a parsing bug that merely looks plausible.

- [ ] **Step 7: Build and commit**

```bash
cd web && pnpm test && pnpm build
git add web/
git commit -m "Add signal history with per-signal rationale and vote breakdown"
```

---

### Task 6: Positions page

**Files:**
- Modify: `web/src/app/positions/page.tsx`
- Create: `web/src/components/PositionsTable.tsx`, `web/src/components/FillsTable.tsx`

**Interfaces:**
- Consumes: `getOpenPositions`, `getTrades`, formatters
- Produces: nothing

- [ ] **Step 1: Fetch both sets on the server**

`getOpenPositions()` for the open rows, `getTrades({ source: "live", limit: 50 })` for recent fills. Render closed trades only in the fills table.

- [ ] **Step 2: Build `PositionsTable`**

Columns: ticker, direction, entry, stop, target, shares, opened-at, and distance-to-stop and distance-to-target **as of entry**.

**Do not render live or unrealized P&L.** There is no quote feed behind this dashboard, so any "current" number would be fabricated from the entry price. State plainly in the panel that no live price feed is wired and the distances are as of entry. This is a deliberate refusal, not an omission.

The five currently-open positions were opened 2026-07-15 and have not moved since. Label anything opened more than a day ago as stale so it is not mistaken for an active position.

- [ ] **Step 3: Build `FillsTable`**

Columns: ticker, direction, entry, exit, outcome, P&L, bars held, closed-at. Newest first, WIN green and LOSS red.

- [ ] **Step 4: Verify**

Load `http://localhost:3000/positions` and confirm 5 open positions and 15 closed fills, the stale labels appear, and no P&L column exists on the open table. Cross-check the count:

```bash
sqlite3 papertrader.db "select outcome, count(*) from trades where source='live' group by 1;"
```

Expected: `LOSS|12`, `OPEN|5`, `WIN|3`.

- [ ] **Step 5: Build and commit**

```bash
cd web && pnpm test && pnpm build
git add web/
git commit -m "Add positions page with open trades and recent fills"
```

---

## Phase 1 exit criteria

- [ ] `cd web && pnpm test` passes with all `lib/` tests green
- [ ] `cd web && pnpm build` succeeds with no type errors
- [ ] All three routes render against the live Flask API with no console errors
- [ ] Overview defaults to live-only and states so; `?source=all` switches and the numbers change
- [ ] The sub-50-trade provisional warning is visible
- [ ] Expectancy is shown gross AND net of an adjustable cost
- [ ] Every signal expands to show all six votes and its reasoning with an accurate provenance label
- [ ] `/positions` shows no fabricated live P&L
- [ ] No `fetch` call and no domain logic exists inside any component under `src/components/`
- [ ] No `any` in the codebase

## Self-review notes

**Spec coverage:** Spec §"`/` overview" → Tasks 3, 4. §"`/signals`" → Task 5. §"`/positions`" → Task 6. §"Architecture" (lib seam, RSC boundary) → Tasks 1, 2. §"Testing" (Vitest over lib, no DOM) → Tasks 1, 2.

**Deliberately deferred to a later phase:** `scripts/export_snapshot.py` and the Vercel deployment. The spec settles the approach — committed snapshot for the deployed build, Flask for local dev — but nothing consumes it until these types exist and stabilize. Building the exporter before the UI proves the shapes would mean guessing at the format.

**Backtest corpus excluded from the eventual snapshot** by decision, keeping it at 269 rows. Revisit after seeing the UI with real data.

**Known limits, named rather than hidden:** client-side filtering breaks somewhere past a few thousand signals (Task 5 Step 1 documents it at the call site); `/api/open` has no source filter, which is currently harmless because every open trade is live; `/api/alerts` likewise. None block this phase.

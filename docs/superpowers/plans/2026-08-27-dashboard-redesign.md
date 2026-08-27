# Instrument Dashboard Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Next.js dashboard the "Instrument" design language and a denser information architecture that consumes the nine metrics fields the API already returns and the UI currently discards.

**Architecture:** Plain CSS with custom properties, split from one 543-line `globals.css` into six files under `web/src/styles/`. Derived values are pure functions in `web/src/lib/` with vitest coverage; components stay props-in/markup-out. No new runtime dependency. Recharts stays.

**Tech Stack:** Next.js 16.3.3 (App Router), React 19.2.8, TypeScript, plain CSS, Recharts 3.10, vitest 4.1.11, pnpm 10.33.

**Spec:** `docs/superpowers/specs/2026-08-27-dashboard-redesign-design.md`

## Global Constraints

- Work in `web/`. All commands run from `web/`. Package manager is **pnpm**, never npm or yarn.
- Baseline before starting: **74 tests across 6 files pass.** That number only goes up.
- Every task ends with `pnpm test`, `pnpm lint`, and `pnpm build` clean.
- No new runtime dependency. No Tailwind. No CSS-in-JS. No component-mounting tests.
- Structural teal (`--accent`) never encodes a number's sign. Mint/coral (`--win`/`--loss`) never appear on chrome.
- Every foreground token must clear **WCAG AA (4.5:1)** against `--ground` and against the composited surface `#101423`.
- All numerals render in IBM Plex Mono with `font-variant-numeric: tabular-nums`.
- `prefers-reduced-motion: reduce` disables every transition and animation.
- **Copy that must survive verbatim** — these carry the project's honesty and are not to be trimmed for visual tidiness:
  - The `PositionsTable` note beginning "No live price feed is wired into this dashboard."
  - The `ProvenanceBand` provisional warning naming `PROVISIONAL_FLOOR`.
  - The `ProvenanceBand` blend warning ("...are not a live track record...").
  - The `CostAdjustedExpectancy` note ("Backtest analysis found the strategy's edge sits below realistic transaction costs.").
  - The `RationalePanel` ATR arithmetic footnote and the WAIT stand-aside sentence.
  - The `error.tsx` "could not reach its data API" explanation.
- Empty states are restyled, never removed: "No open positions.", "No closed trades yet.", "No signals match these filters.", "Not enough closed trades to plot", "No rows.", "No indicator votes recorded for this signal."
- Commit after each task. Never commit to `main`. Never push.

---

### Task 1: Split `globals.css` by responsibility

Mechanical move only. Zero visual change — this commit must be reviewable as "nothing moved on screen".

**Files:**
- Create: `web/src/styles/shell.css`, `web/src/styles/cards.css`, `web/src/styles/tables.css`, `web/src/styles/signals.css`
- Modify: `web/src/app/globals.css`

**Interfaces:**
- Consumes: nothing.
- Produces: four stylesheets imported by `globals.css`, so later tasks edit a focused file instead of one long one.

- [ ] **Step 1: Move the shell rules**

Cut these rule blocks out of `globals.css` and paste them, unchanged, into `web/src/styles/shell.css`: `.nav`, `.nav-link`, `.nav-link:hover`, `.page-content`, `.error-detail`.

- [ ] **Step 2: Move the card rules**

Cut into `web/src/styles/cards.css`, unchanged: `.stat-grid`, `.stat-tile`, `.stat-tile-label`, `.stat-tile-value`, `.stat-tile-value-positive`, `.stat-tile-value-negative`, `.stat-tile-value-neutral`, `.stat-tile-note`, `.provenance-band`, `.provenance-statement`, `.provenance-warning`, `.cost-adjusted-expectancy`, `.cost-adjusted-row`, `.cost-adjusted-stat`, `.cost-adjusted-input`, `.cost-adjusted-input input`, `.cost-adjusted-note`, `.equity-curve`, `.equity-curve-empty`, `.tone-positive`, `.tone-negative`, `.tone-muted`.

- [ ] **Step 3: Move the table rules**

Cut into `web/src/styles/tables.css`, unchanged: every `.breakdown-table*` rule, `.breakdown-empty`, every `.positions-table*` and `.fills-table*` rule, `.positions-note`, `.positions-stale-badge`, `.positions-empty`, `.fills-empty`, and every `.vote-table*` rule.

- [ ] **Step 4: Move the signal rules**

Cut into `web/src/styles/signals.css`, unchanged: `.filter-bar`, `.filter-field`, `.filter-field select, .filter-field input`, `.signal-list-count`, `.signal-rows`, `.signal-list-empty`, every `.signal-row*` rule, `.signal-badge`, and every `.rationale-*` rule.

- [ ] **Step 5: Reduce `globals.css` to imports plus the reset**

`globals.css` keeps only `:root`, the `html`/`body`/`*` reset, and the `a` rules it already has. Put the imports at the very top — CSS requires `@import` to precede other rules:

```css
@import "../styles/shell.css";
@import "../styles/cards.css";
@import "../styles/tables.css";
@import "../styles/signals.css";

:root {
  /* ...existing token block, unchanged... */
}
```

- [ ] **Step 6: Verify nothing moved**

Run: `pnpm build && pnpm lint && pnpm test`
Expected: build succeeds, lint clean, 74 tests pass.

Then run `pnpm dev`, open `http://localhost:3000`, and confirm all three pages look **identical** to before. If anything shifted, a rule was dropped in the move — diff the old `globals.css` against the concatenation of the five files.

- [ ] **Step 7: Commit**

```bash
git add web/src/styles web/src/app/globals.css
git commit -m "Split globals.css by responsibility"
```

---

### Task 2: Palette, type, and backdrop

**Files:**
- Create: `web/src/styles/tokens.css`, `web/src/styles/base.css`
- Modify: `web/src/app/globals.css`, `web/src/app/layout.tsx`

**Interfaces:**
- Consumes: the file split from Task 1.
- Produces: the custom properties every later task styles against — `--ground`, `--surface`, `--surface-2`, `--line`, `--line-strong`, `--ink`, `--muted`, `--faint`, `--accent`, `--caution`, `--win`, `--loss`, `--radius`, `--radius-sm`, `--font-display`, `--font-sans`, `--font-mono`.

- [ ] **Step 1: Write the token sheet**

Create `web/src/styles/tokens.css`:

```css
:root {
  --ground: #04060b;
  --surface: rgba(150, 180, 255, 0.05);
  --surface-2: rgba(150, 180, 255, 0.08);
  --line: rgba(150, 180, 255, 0.13);
  --line-strong: rgba(150, 180, 255, 0.26);

  --ink: #e9effa;
  --muted: #91a0ba;
  --faint: #77859f;

  --accent: #35e8d2;
  --caution: #ffb454;
  --win: #4ade80;
  --loss: #ff6b6b;

  --radius: 10px;
  --radius-sm: 6px;
  --space: 8px;

  --rail-width: 200px;
  --canvas: 1400px;

  color-scheme: dark;
}
```

The old `--bg`, `--panel`, `--fg`, `--green`, `--red` names are gone. Every rule that referenced them is updated in this task: `--bg` becomes `--ground`, `--panel` becomes `--surface`, `--fg` becomes `--ink`, `--green` becomes `--win`, `--red` becomes `--loss`. Search for them with `grep -rn "var(--bg)\|var(--panel)\|var(--fg)\|var(--green)\|var(--red)" web/src` and fix every hit before moving on.

- [ ] **Step 2: Write the base sheet**

Create `web/src/styles/base.css`. The backdrop lives on `body::before` (grid field, masked so it fades out) and `body::after` (two anchored glows), both at `z-index: -1` so page content needs no stacking context of its own:

```css
* {
  box-sizing: border-box;
  padding: 0;
  margin: 0;
}

html {
  height: 100%;
}

html,
body {
  max-width: 100vw;
  overflow-x: hidden;
}

body {
  min-height: 100%;
  display: flex;
  color: var(--ink);
  background: var(--ground);
  font-family: var(--font-sans);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

body::before {
  content: "";
  position: fixed;
  inset: 0;
  z-index: -1;
  pointer-events: none;
  background-image:
    linear-gradient(to right, rgba(150, 180, 255, 0.055) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(150, 180, 255, 0.055) 1px, transparent 1px);
  background-size: 64px 64px;
  -webkit-mask-image: radial-gradient(ellipse 120% 80% at 50% 0%, #000, transparent 70%);
  mask-image: radial-gradient(ellipse 120% 80% at 50% 0%, #000, transparent 70%);
}

body::after {
  content: "";
  position: fixed;
  inset: 0;
  z-index: -1;
  pointer-events: none;
  background:
    radial-gradient(900px 500px at 15% -10%, rgba(53, 232, 210, 0.1), transparent 62%),
    radial-gradient(800px 520px at 88% 110%, rgba(255, 180, 84, 0.05), transparent 60%);
}

h1,
h2,
h3 {
  font-family: var(--font-display);
  letter-spacing: -0.03em;
  font-weight: 600;
}

a {
  color: var(--accent);
  text-decoration: none;
}

a:hover {
  text-decoration: underline;
}

:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
  border-radius: var(--radius-sm);
}

.num {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}

.micro {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  color: var(--faint);
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

Note `body` is now `display: flex` in row direction — the rail sits beside the content. Task 4 adds the content column.

- [ ] **Step 3: Reduce `globals.css` to an import list**

`globals.css` becomes exactly this and nothing else. The `:root` block and reset it used to hold now live in `tokens.css` and `base.css`:

```css
@import "../styles/tokens.css";
@import "../styles/base.css";
@import "../styles/shell.css";
@import "../styles/cards.css";
@import "../styles/tables.css";
@import "../styles/signals.css";
```

- [ ] **Step 4: Swap the fonts**

In `web/src/app/layout.tsx`, replace the Geist imports and the `html` className. Space Grotesk is a variable font; the two IBM Plex families need explicit weights:

```tsx
import { Space_Grotesk, IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";

const display = Space_Grotesk({
  variable: "--font-display",
  subsets: ["latin"],
});

const sans = IBM_Plex_Sans({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const mono = IBM_Plex_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});
```

and

```tsx
<html lang="en" className={`${display.variable} ${sans.variable} ${mono.variable}`}>
```

`--font-geist-mono` is referenced by `.error-detail` in `shell.css`; change it to `var(--font-mono, monospace)`.

- [ ] **Step 5: Verify contrast before trusting the palette**

This is a gate, not a formality. Write a throwaway checker in the scratchpad — do not commit it:

```bash
cat > /tmp/contrast.mjs <<'JS'
const lin = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
const lum = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const ground = hex("#04060b");
// --surface-2 rgba(150,180,255,0.08) composited over --ground
const surface = [150, 180, 255].map((c, i) => Math.round(c * 0.08 + ground[i] * 0.92));
for (const [name, h] of Object.entries({
  ink: "#e9effa", muted: "#91a0ba", faint: "#77859f",
  accent: "#35e8d2", caution: "#ffb454", win: "#4ade80", loss: "#ff6b6b",
})) {
  const g = ratio(hex(h), ground), s = ratio(hex(h), surface);
  console.log(name.padEnd(8), "ground", g.toFixed(2), g >= 4.5 ? "PASS" : "FAIL",
              "| surface", s.toFixed(2), s >= 4.5 ? "PASS" : "FAIL");
}
JS
node /tmp/contrast.mjs
```

Expected: every row PASS on both columns. If `--faint` fails, lighten it until it passes and update `tokens.css` — it is used for the `.micro` labels, which are small text and get no large-text exemption. Record the final numbers in the commit body.

- [ ] **Step 6: Verify the build**

Run: `pnpm test && pnpm lint && pnpm build`
Expected: 74 tests pass, lint clean, build succeeds.

Then `pnpm dev` and confirm on all three pages: the grid field is visible near the top and fades out, glows sit top-left and bottom-right, all numbers are monospaced, headings are Space Grotesk. Toggle "Reduce motion" in macOS System Settings → Accessibility → Display and confirm nothing animates.

- [ ] **Step 7: Commit**

```bash
git add web/src/styles web/src/app/globals.css web/src/app/layout.tsx
git commit -m "Adopt the Instrument palette, type stack, and backdrop"
```

---

### Task 3: Pure logic in `lib/`

Straight TDD. No component touches this task.

**Files:**
- Modify: `web/src/lib/costs.ts`, `web/src/lib/costs.test.ts`, `web/src/lib/indicators.ts`
- Create: `web/src/lib/levels.ts`, `web/src/lib/levels.test.ts`, `web/src/lib/scale.ts`, `web/src/lib/scale.test.ts`, `web/src/lib/breakdowns.ts`, `web/src/lib/breakdowns.test.ts`

**Interfaces:**
- Consumes: `Breakdown` from `@/lib/types`.
- Produces:
  - `breakEvenCost(grossExpectancy: number): number` — `@/lib/costs`
  - `entryFraction(stop: number, entry: number, target: number): number | null` — `@/lib/levels`
  - `shareOfMax(values: number[]): number[]` — `@/lib/scale`
  - `breakdownRows(rows: Record<string, Breakdown>): BreakdownRow[]` and `interface BreakdownRow extends Breakdown { name: string; share: number }` — `@/lib/breakdowns`
  - `CONFIDENCE_THRESHOLD: number` — `@/lib/indicators`

- [ ] **Step 1: Write the failing tests**

Append to `web/src/lib/costs.test.ts` (and add `breakEvenCost` to its import from `@/lib/costs`):

```ts
describe("breakEvenCost", () => {
  it("is the gross edge itself when the edge is positive", () => {
    expect(breakEvenCost(3.05)).toBeCloseTo(3.05);
  });

  it("reports zero for an edge that is already negative", () => {
    expect(breakEvenCost(-14.79)).toBe(0);
  });

  it("reports zero for a flat edge", () => {
    expect(breakEvenCost(0)).toBe(0);
  });
});
```

Create `web/src/lib/levels.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { entryFraction } from "@/lib/levels";

describe("entryFraction", () => {
  it("puts a 2:1 long entry one third along the axis", () => {
    expect(entryFraction(95, 100, 110)).toBeCloseTo(1 / 3);
  });

  it("puts a 2:1 short entry one third along the axis", () => {
    expect(entryFraction(105, 100, 90)).toBeCloseTo(1 / 3);
  });

  it("returns null when stop and target are the same price", () => {
    expect(entryFraction(100, 100, 100)).toBeNull();
  });

  it("reports a fraction outside the axis rather than clamping it", () => {
    expect(entryFraction(95, 120, 110)).toBeCloseTo(5 / 3);
  });
});
```

Create `web/src/lib/scale.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { shareOfMax } from "@/lib/scale";

describe("shareOfMax", () => {
  it("scales each magnitude against the largest", () => {
    expect(shareOfMax([10, -5, 2.5])).toEqual([1, 0.5, 0.25]);
  });

  it("ignores sign when sizing", () => {
    expect(shareOfMax([-10, 10])).toEqual([1, 1]);
  });

  it("returns all zeroes when every value is zero", () => {
    expect(shareOfMax([0, 0])).toEqual([0, 0]);
  });

  it("returns an empty array for no values", () => {
    expect(shareOfMax([])).toEqual([]);
  });
});
```

Create `web/src/lib/breakdowns.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { breakdownRows } from "@/lib/breakdowns";
import type { Breakdown } from "@/lib/types";

const row = (n: number, wins: number, pnl: number): Breakdown => ({
  n,
  wins,
  win_rate: n === 0 ? 0 : wins / n,
  pnl,
});

describe("breakdownRows", () => {
  it("sorts by P&L, most profitable first", () => {
    const rows = breakdownRows({ AAPL: row(10, 4, -20), NVDA: row(10, 6, 40) });
    expect(rows.map((r) => r.name)).toEqual(["NVDA", "AAPL"]);
  });

  it("sizes each bar against the largest magnitude, not the largest gain", () => {
    const rows = breakdownRows({ NVDA: row(10, 6, 40), AAPL: row(10, 2, -80) });
    expect(rows.find((r) => r.name === "AAPL")?.share).toBe(1);
    expect(rows.find((r) => r.name === "NVDA")?.share).toBe(0.5);
  });

  it("carries the original breakdown fields through", () => {
    const [only] = breakdownRows({ SPY: row(8, 2, 5) });
    expect(only).toMatchObject({ name: "SPY", n: 8, wins: 2, pnl: 5 });
  });

  it("returns an empty array for no rows", () => {
    expect(breakdownRows({})).toEqual([]);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pnpm test`
Expected: FAIL — `levels.ts`, `scale.ts` and `breakdowns.ts` do not resolve, and `breakEvenCost` is not exported.

- [ ] **Step 3: Write the implementations**

Append to `web/src/lib/costs.ts`:

```ts
// The cost per trade at which net expectancy reaches zero. An edge that is already at or
// below zero has no such crossing, so it reports zero rather than a negative cost.
export function breakEvenCost(grossExpectancy: number): number {
  return grossExpectancy > 0 ? grossExpectancy : 0;
}
```

Create `web/src/lib/levels.ts`:

```ts
// Where entry sits on the stop-to-target axis, as a fraction. Works for both directions:
// a SHORT has its target below its stop, which flips the sign of numerator and
// denominator together. Deliberately unclamped — a fraction outside 0..1 means a
// malformed level set, and clamping here would hide that from the caller.
export function entryFraction(stop: number, entry: number, target: number): number | null {
  const span = target - stop;
  if (span === 0) return null;
  const fraction = (entry - stop) / span;
  return Number.isFinite(fraction) ? fraction : null;
}
```

Create `web/src/lib/scale.ts`:

```ts
export function shareOfMax(values: number[]): number[] {
  const largest = Math.max(0, ...values.map((value) => Math.abs(value)));
  return values.map((value) => (largest === 0 ? 0 : Math.abs(value) / largest));
}
```

Create `web/src/lib/breakdowns.ts`:

```ts
import type { Breakdown } from "@/lib/types";
import { shareOfMax } from "@/lib/scale";

export interface BreakdownRow extends Breakdown {
  name: string;
  share: number;
}

export function breakdownRows(rows: Record<string, Breakdown>): BreakdownRow[] {
  const entries = Object.entries(rows);
  const shares = shareOfMax(entries.map(([, breakdown]) => breakdown.pnl));
  return entries
    .map(([name, breakdown], index) => ({ ...breakdown, name, share: shares[index] }))
    .sort((a, b) => b.pnl - a.pnl);
}
```

Append to `web/src/lib/indicators.ts`:

```ts
// Mirrors config.CONFIDENCE_THRESHOLD in the Python engine (config.py), which compares
// with >=. Kept in sync by hand; the engine is the authority.
export const CONFIDENCE_THRESHOLD = 0.62;
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pnpm test`
Expected: PASS — 6 files grow to 9, and the test count rises from 74 to 89.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib
git commit -m "Add derived-value helpers for the redesigned dashboard"
```

---

### Task 4: The shell — side rail and global scope

**Files:**
- Create: `web/src/components/SideRail.tsx`
- Delete: `web/src/components/Nav.tsx`
- Modify: `web/src/app/layout.tsx`, `web/src/styles/shell.css`, `web/src/app/signals/page.tsx`, `web/src/app/positions/page.tsx`

**Interfaces:**
- Consumes: tokens from Task 2.
- Produces: the `.rail`, `.canvas`, `.page-head` and `.segmented` classes that Tasks 5–7 lay out inside; and the `?source=` param honored by all three routes.

**Deviation from the spec, deliberate:** the spec's rail scope block says "with counts". Counts would force a `getMetrics` call in `layout.tsx` on every navigation, duplicating the fetch that `page.tsx` already makes — the exact duplication commit `74a50f4` removed. The rail therefore carries the scope toggle only, and each page shows its own counts in its header.

- [ ] **Step 1: Write the rail**

Create `web/src/components/SideRail.tsx`. It needs the active route and the current scope, so it is a client component:

```tsx
"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/signals", label: "Signals" },
  { href: "/positions", label: "Positions" },
];

export default function SideRail() {
  const pathname = usePathname();
  const scope = useSearchParams().get("source") === "all" ? "all" : "live";
  const keepScope = (href: string) => (scope === "all" ? `${href}?source=all` : href);

  return (
    <aside className="rail">
      <Link href={keepScope("/")} className="rail-mark">
        PT<span className="rail-mark-slash">//</span>26
      </Link>

      <nav className="rail-nav" aria-label="Primary">
        {LINKS.map((link) => (
          <Link
            key={link.href}
            href={keepScope(link.href)}
            className={`rail-link${pathname === link.href ? " rail-link-active" : ""}`}
            aria-current={pathname === link.href ? "page" : undefined}
          >
            {link.label}
          </Link>
        ))}
      </nav>

      <div className="rail-scope">
        <span className="micro">Scope</span>
        <div className="segmented">
          <Link
            href={pathname}
            className={`segmented-option${scope === "live" ? " segmented-option-active" : ""}`}
          >
            Live
          </Link>
          <Link
            href={`${pathname}?source=all`}
            className={`segmented-option${scope === "all" ? " segmented-option-active" : ""}`}
          >
            All
          </Link>
        </div>
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: Mount it behind a Suspense boundary**

`useSearchParams` forces a Suspense boundary during prerender; without one, `pnpm build` fails with a CSR-bailout error. In `web/src/app/layout.tsx`, replace the `Nav` import and usage:

```tsx
import { Suspense } from "react";
import SideRail from "@/components/SideRail";
```

```tsx
<body>
  <Suspense fallback={<aside className="rail" />}>
    <SideRail />
  </Suspense>
  <div className="canvas">{children}</div>
</body>
```

Then `rm web/src/components/Nav.tsx`.

- [ ] **Step 3: Style the shell**

Replace the `.nav`, `.nav-link`, `.nav-link:hover` and `.page-content` rules in `web/src/styles/shell.css` with:

```css
.rail {
  position: sticky;
  top: 0;
  align-self: flex-start;
  display: flex;
  flex-direction: column;
  gap: calc(var(--space) * 4);
  width: var(--rail-width);
  flex: 0 0 var(--rail-width);
  height: 100vh;
  padding: calc(var(--space) * 3);
  border-right: 1px solid var(--line);
  background: var(--surface);
}

.rail-mark {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  letter-spacing: 0.2em;
  color: var(--faint);
}

.rail-mark:hover {
  color: var(--ink);
  text-decoration: none;
}

.rail-mark-slash {
  color: var(--accent);
}

.rail-nav {
  display: flex;
  flex-direction: column;
  gap: calc(var(--space) / 2);
}

.rail-link {
  padding: calc(var(--space) * 0.75) var(--space);
  border-radius: var(--radius-sm);
  color: var(--muted);
  font-size: 0.9rem;
  font-weight: 500;
  transition: color 150ms, background-color 150ms;
}

.rail-link:hover {
  background: var(--surface-2);
  color: var(--ink);
  text-decoration: none;
}

.rail-link-active {
  background: var(--surface-2);
  color: var(--ink);
  box-shadow: inset 2px 0 0 var(--accent);
}

.rail-scope {
  display: flex;
  flex-direction: column;
  gap: var(--space);
  margin-top: auto;
}

.segmented {
  display: inline-flex;
  gap: 2px;
  padding: 2px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: var(--ground);
}

.segmented-option {
  flex: 1;
  padding: calc(var(--space) / 2) var(--space);
  border: none;
  border-radius: 4px;
  background: none;
  color: var(--muted);
  font: inherit;
  font-size: 0.8rem;
  text-align: center;
  cursor: pointer;
  transition: color 150ms, background-color 150ms;
}

.segmented-option:hover {
  color: var(--ink);
  text-decoration: none;
}

.segmented-option-active {
  background: var(--surface-2);
  color: var(--ink);
  box-shadow: inset 0 0 0 1px var(--line-strong);
}

.canvas {
  flex: 1;
  min-width: 0;
  max-width: var(--canvas);
  padding: calc(var(--space) * 4);
}

.page-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: calc(var(--space) * 2);
  margin-bottom: calc(var(--space) * 3);
}

@media (max-width: 900px) {
  body {
    flex-direction: column;
  }

  .rail {
    position: static;
    flex-direction: row;
    align-items: center;
    width: 100%;
    flex-basis: auto;
    height: auto;
    gap: calc(var(--space) * 2);
    border-right: none;
    border-bottom: 1px solid var(--line);
  }

  .rail-nav {
    flex-direction: row;
  }

  .rail-scope {
    flex-direction: row;
    align-items: center;
    margin-top: 0;
    margin-left: auto;
  }

  .canvas {
    padding: calc(var(--space) * 2);
  }
}
```

Keep `.page-content` for now — Tasks 5–7 replace its uses with `.canvas` children. Delete it in Task 8 once nothing references it.

- [ ] **Step 4: Thread the scope through the two pages that hardcode it**

`web/src/app/signals/page.tsx` — give it search params and derive the scope the same way `page.tsx` already does:

```tsx
export default async function SignalsPage({
  searchParams,
}: {
  searchParams: Promise<{ source?: string }>;
}) {
  const { source } = await searchParams;
  const scope = source === "all" ? undefined : "live";

  const signals = await getSignals({ source: scope, limit: 500 });
  const trades = await getTrades({ source: scope, limit: 500 });
```

Update its `ScopeNote` copy so it stays true under both scopes:

```tsx
<ScopeNote>
  {scope === "live"
    ? `Showing ${signals.length} live signals. Backtest replay signals are excluded from this view.`
    : `Showing ${signals.length} signals, live and backtest replay combined. Replay signals come from a different period.`}
</ScopeNote>
```

`web/src/app/positions/page.tsx` — same treatment for the `getTrades` call and its `ScopeNote`. `getOpenPositions()` takes no source and stays as it is; open positions are live by definition.

- [ ] **Step 5: Verify**

Run: `pnpm test && pnpm lint && pnpm build`
Expected: 89 tests pass, lint clean, build succeeds. A build failure mentioning `useSearchParams` and "missing suspense boundary" means Step 2's `<Suspense>` wrapper was skipped.

Then `pnpm dev` and check: the rail is fixed at the left, the active route shows a teal inset bar, clicking Live/All changes the URL and the row counts on every page, and navigating between pages preserves the chosen scope. Narrow the window below 900px and confirm the rail becomes a top bar.

- [ ] **Step 6: Commit**

```bash
git add web/src/components web/src/app web/src/styles/shell.css
git commit -m "Replace the top nav with a side rail carrying global scope"
```

---

### Task 5: Overview

**Files:**
- Create: `web/src/components/HeroStat.tsx`, `web/src/components/RatioBar.tsx`, `web/src/components/WinLossCard.tsx`, `web/src/components/RMultipleCard.tsx`
- Modify: `web/src/app/page.tsx`, `web/src/components/ProvenanceBand.tsx`, `web/src/components/StatTile.tsx`, `web/src/components/CostAdjustedExpectancy.tsx`, `web/src/components/BreakdownTable.tsx`, `web/src/components/EquityCurve.tsx`, `web/src/styles/cards.css`, `web/src/styles/tables.css`

**Interfaces:**
- Consumes: `breakEvenCost` from `@/lib/costs`, `breakdownRows`/`BreakdownRow` from `@/lib/breakdowns`, tokens and `.canvas`/`.page-head` from Tasks 2 and 4.
- Produces: `HeroStat` (props `{ label: string; value: string; tone: "positive" | "negative"; qualifier: ReactNode; children?: ReactNode }`) and `RatioBar` (props `{ left: number; right: number; leftLabel: string; rightLabel: string }`), both reused nowhere else but kept as components so `page.tsx` stays markup.

- [ ] **Step 1: Write `HeroStat` and `RatioBar`**

`web/src/components/HeroStat.tsx`:

```tsx
import type { ReactNode } from "react";

export interface HeroStatProps {
  label: string;
  value: string;
  tone: "positive" | "negative";
  qualifier: ReactNode;
  children?: ReactNode;
}

export default function HeroStat({ label, value, tone, qualifier, children }: HeroStatProps) {
  return (
    <header className="hero">
      <p className="micro">{label}</p>
      <p className={`hero-value num tone-${tone}`}>{value}</p>
      <p className="hero-qualifier">{qualifier}</p>
      {children}
    </header>
  );
}
```

`web/src/components/RatioBar.tsx`:

```tsx
export interface RatioBarProps {
  left: number;
  right: number;
  leftLabel: string;
  rightLabel: string;
}

export default function RatioBar({ left, right, leftLabel, rightLabel }: RatioBarProps) {
  const total = left + right;
  const leftPercent = total === 0 ? 0 : (left / total) * 100;

  return (
    <div className="ratio">
      <div className="ratio-track" role="img" aria-label={`${left} ${leftLabel}, ${right} ${rightLabel}`}>
        <div className="ratio-fill-left" style={{ width: `${leftPercent}%` }} />
      </div>
      <div className="ratio-legend">
        <span className="tone-positive num">{left} {leftLabel}</span>
        <span className="tone-negative num">{right} {rightLabel}</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Write the two composite cards**

`web/src/components/WinLossCard.tsx`:

```tsx
import RatioBar from "@/components/RatioBar";
import { formatCurrency, formatPercent } from "@/lib/format";

export interface WinLossCardProps {
  nWins: number;
  nLosses: number;
  winRate: number;
  avgWin: number;
  avgLoss: number;
}

export default function WinLossCard({ nWins, nLosses, winRate, avgWin, avgLoss }: WinLossCardProps) {
  return (
    <section className="card">
      <h2 className="micro">Win / loss</h2>
      <p className="card-figure num">{formatPercent(winRate)}</p>
      <RatioBar left={nWins} right={nLosses} leftLabel="wins" rightLabel="losses" />
      <dl className="pair-grid">
        <div>
          <dt className="micro">Avg win</dt>
          <dd className="num tone-positive">{formatCurrency(avgWin)}</dd>
        </div>
        <div>
          <dt className="micro">Avg loss</dt>
          <dd className="num tone-negative">{formatCurrency(avgLoss)}</dd>
        </div>
      </dl>
    </section>
  );
}
```

`web/src/components/RMultipleCard.tsx`:

```tsx
import { formatR } from "@/lib/format";

export interface RMultipleCardProps {
  avgR: number;
  avgWinR: number;
  avgLossR: number;
}

export default function RMultipleCard({ avgR, avgWinR, avgLossR }: RMultipleCardProps) {
  return (
    <section className="card">
      <h2 className="micro">R-multiples</h2>
      <p className={`card-figure num tone-${avgR >= 0 ? "positive" : "negative"}`}>{formatR(avgR)}</p>
      <dl className="pair-grid">
        <div>
          <dt className="micro">Avg win</dt>
          <dd className="num tone-positive">{formatR(avgWinR)}</dd>
        </div>
        <div>
          <dt className="micro">Avg loss</dt>
          <dd className="num tone-negative">{formatR(avgLossR)}</dd>
        </div>
      </dl>
      <p className="card-note">
        Realized R against the 2:1 reward-to-risk the engine targets at entry.
      </p>
    </section>
  );
}
```

- [ ] **Step 3: Show the break-even cost in `CostAdjustedExpectancy`**

Import `breakEvenCost` alongside the existing imports and add a third stat plus a crossing sentence. The existing note text stays exactly as it is. Insert after the `Net` stat block:

```tsx
<div className="cost-adjusted-stat">
  <div className="micro">Breaks even at</div>
  <div className="num card-figure-sm">
    {breakEven > 0 ? `${formatPrice(breakEven)}/trade` : "—"}
  </div>
</div>
```

with `const breakEven = breakEvenCost(grossExpectancy);` beside the existing `net`, and `formatPrice` added to the `@/lib/format` import. Below the row, above the existing note:

```tsx
<p className="cost-adjusted-crossing">
  {breakEven > 0
    ? `Net expectancy reaches zero at ${formatPrice(breakEven)} of cost per trade. Above that, the edge is gone.`
    : "Gross expectancy is already at or below zero, so no cost level makes this profitable."}
</p>
```

- [ ] **Step 4: Move the sort out of `BreakdownTable` and add the inline bar**

Replace the component body's `sorted` computation with `breakdownRows(rows)` from `@/lib/breakdowns`, and render the bar behind the P&L cell:

```tsx
<td className={`num ${row.pnl >= 0 ? "tone-positive" : "tone-negative"}`}>
  <span className="cell-bar" style={{ width: `${row.share * 100}%` }} aria-hidden="true" />
  <span className="cell-value">{formatCurrency(row.pnl)}</span>
</td>
```

The containing `<td>` needs `position: relative`; the bar is absolutely positioned inside it at low opacity so the number stays readable. Add to `web/src/styles/tables.css`:

```css
.breakdown-table td:last-child,
.fills-table td.pnl-cell {
  position: relative;
  isolation: isolate;
}

.cell-bar {
  position: absolute;
  inset: 2px auto 2px 0;
  z-index: -1;
  border-radius: 2px;
  background: currentColor;
  opacity: 0.14;
}

.cell-value {
  position: relative;
}
```

- [ ] **Step 5: Restyle `ProvenanceBand` as the hero qualifier**

It stops being a card and becomes inline text under the hero. Change the wrapper `className` from `provenance-band` to `provenance`, the statement to `provenance-statement micro`, and prefix each warning with a caution marker:

```tsx
<p className="provenance-warning">
  <span aria-hidden="true">⚠ </span>
  Provisional: only {nClosed} closed trades. The project&apos;s evaluation floor is{" "}
  {PROVISIONAL_FLOOR} closed trades — no conclusion should be drawn from this sample yet.
</p>
```

The wording of both warnings is unchanged. Only the wrapper classes and the marker are new.

- [ ] **Step 6: Rebuild the page grid**

`web/src/app/page.tsx` keeps its existing data fetching exactly as it is — including the `bandSource` logic and the conditional second `getMetrics` call — and changes only what it renders:

```tsx
<main className="canvas">
  <HeroStat
    label="Total P&L"
    value={formatCurrency(metrics.total_pnl)}
    tone={metrics.total_pnl >= 0 ? "positive" : "negative"}
    qualifier={
      <>
        <span className="num">{metrics.n_closed}</span> closed ·{" "}
        <span className="num">{formatPercent(metrics.win_rate)}</span> win ·{" "}
        <span className="num">{metrics.n_open}</span> open
      </>
    }
  >
    <ProvenanceBand source={bandSource} nClosed={metrics.n_closed} nLiveClosed={nLiveClosed} />
  </HeroStat>

  <div className="grid-8-4">
    <EquityCurve points={metrics.equity} />
    <WinLossCard
      nWins={metrics.n_wins}
      nLosses={metrics.n_losses}
      winRate={metrics.win_rate}
      avgWin={metrics.avg_win}
      avgLoss={metrics.avg_loss}
    />
  </div>

  <div className="stat-grid">
    <StatTile
      label="Expectancy"
      value={formatCurrency(metrics.expectancy)}
      tone={metrics.expectancy >= 0 ? "positive" : "negative"}
    />
    <StatTile
      label="Profit factor"
      value={metrics.profit_factor === null ? "—" : formatRatio(metrics.profit_factor)}
      tone={metrics.profit_factor !== null && metrics.profit_factor >= 1 ? "positive" : "negative"}
    />
    <StatTile
      label="Max drawdown"
      value={`${formatCurrency(-metrics.max_drawdown)} (${formatPercent(metrics.max_drawdown_pct)})`}
      tone="negative"
    />
    <StatTile label="Avg bars held" value={formatRatio(metrics.avg_bars_held)} />
  </div>

  <div className="grid-6-6">
    <CostAdjustedExpectancy grossExpectancy={metrics.expectancy} />
    <RMultipleCard
      avgR={metrics.avg_r_multiple}
      avgWinR={metrics.avg_win_r}
      avgLossR={metrics.avg_loss_r}
    />
  </div>

  <div className="grid-6-6">
    <BreakdownTable title="By regime" rows={metrics.by_regime} />
    <BreakdownTable title="By ticker" rows={metrics.by_ticker} />
  </div>
</main>
```

Add `formatRatio` to the `@/lib/format` import.

- [ ] **Step 7: Style the new pieces**

Add to `web/src/styles/cards.css` — the shared `.card` surface (gradient from `--surface-2` to `--surface` with a hairline top rule, the treatment the whole design leans on), plus `.hero`, `.hero-value`, `.hero-qualifier`, `.provenance`, `.ratio*`, `.pair-grid`, `.card-figure`, `.card-figure-sm`, `.card-note`, `.cost-adjusted-crossing`, and the `.grid-8-4`/`.grid-6-6` layouts:

```css
.card,
.equity-curve,
.cost-adjusted-expectancy,
.stat-tile {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: linear-gradient(to bottom, var(--surface-2), var(--surface));
  padding: calc(var(--space) * 2);
}

.card::before,
.equity-curve::before,
.cost-adjusted-expectancy::before,
.stat-tile::before {
  content: "";
  position: absolute;
  inset-inline: calc(var(--space) * 2);
  top: 0;
  height: 1px;
  background: linear-gradient(to right, transparent, var(--line-strong), transparent);
}

.hero {
  margin-bottom: calc(var(--space) * 4);
}

.hero-value {
  font-size: clamp(2.5rem, 6vw, 4rem);
  font-weight: 600;
  line-height: 1.05;
  letter-spacing: -0.03em;
  margin: calc(var(--space) / 2) 0;
}

.hero-qualifier {
  color: var(--muted);
  font-size: 0.9rem;
}

.provenance-warning {
  margin-top: var(--space);
  color: var(--caution);
  font-size: 0.85rem;
  max-width: 68ch;
}

.grid-8-4,
.grid-6-6 {
  display: grid;
  gap: calc(var(--space) * 2);
  margin-bottom: calc(var(--space) * 2);
}

.grid-8-4 {
  grid-template-columns: 2fr 1fr;
}

.grid-6-6 {
  grid-template-columns: 1fr 1fr;
}

@media (max-width: 1100px) {
  .grid-8-4,
  .grid-6-6 {
    grid-template-columns: 1fr;
  }
}

.ratio-track {
  height: 6px;
  border-radius: 3px;
  background: var(--loss);
  overflow: hidden;
  margin: var(--space) 0;
}

.ratio-fill-left {
  height: 100%;
  background: var(--win);
}

.ratio-legend {
  display: flex;
  justify-content: space-between;
  font-size: 0.8rem;
}

.pair-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space);
  margin-top: calc(var(--space) * 1.5);
}

.card-figure {
  font-size: 1.75rem;
  font-weight: 600;
}

.card-figure-sm {
  font-size: 1.25rem;
  font-weight: 600;
}

.card-note,
.cost-adjusted-crossing {
  margin-top: var(--space);
  color: var(--muted);
  font-size: 0.8rem;
  line-height: 1.5;
}

.cost-adjusted-crossing {
  color: var(--caution);
}
```

Update `.stat-tile-value` to carry tabular figures by adding `font-family: var(--font-mono); font-variant-numeric: tabular-nums;`, then retire the three `.stat-tile-value-*` rules in favour of the shared tone classes.

`StatTile`'s `tone` prop is `"positive" | "negative" | "neutral"`, but the shared class for the third case is `tone-muted`, not `tone-neutral` — so the mapping is explicit, not string interpolation. In `StatTile.tsx`:

```tsx
const TONE_CLASS = {
  positive: "tone-positive",
  negative: "tone-negative",
  neutral: "tone-muted",
} as const;
```

```tsx
<div className={`stat-tile-value ${TONE_CLASS[tone]}`}>{value}</div>
```

`CostAdjustedExpectancy.tsx` builds the same class name inline twice; replace both with `tone-positive`/`tone-negative` chosen by the sign, since neither can be neutral. Then delete `.stat-tile-value-positive`, `.stat-tile-value-negative` and `.stat-tile-value-neutral` from `cards.css`.

- [ ] **Step 8: Restyle the equity curve**

In `EquityCurve.tsx`, swap `LineChart`/`Line` for `AreaChart`/`Area` with a gradient fill, keeping every existing prop and formatter:

```tsx
<AreaChart data={points} margin={{ top: 5, right: 20, bottom: 5, left: 5 }}>
  <defs>
    <linearGradient id="equity-fill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.28} />
      <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
    </linearGradient>
  </defs>
  <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" />
  <XAxis dataKey="label" tickFormatter={formatTimestamp} stroke="var(--faint)" fontSize={11} />
  <YAxis domain={["auto", "auto"]} tickFormatter={formatCurrency} stroke="var(--faint)" fontSize={11} />
  <Tooltip
    labelFormatter={(label) => formatTimestamp(String(label))}
    formatter={(value) => formatCurrency(typeof value === "number" ? value : undefined)}
    contentStyle={{
      background: "var(--ground)",
      border: "1px solid var(--line-strong)",
      borderRadius: "var(--radius-sm)",
    }}
    labelStyle={{ color: "var(--muted)" }}
    itemStyle={{ color: "var(--ink)" }}
  />
  <Area type="monotone" dataKey="equity" stroke="var(--accent)" strokeWidth={2} fill="url(#equity-fill)" />
</AreaChart>
```

Update the import from `recharts` to bring in `Area` and `AreaChart` and drop `Line`/`LineChart`.

- [ ] **Step 9: Verify**

Run: `pnpm test && pnpm lint && pnpm build`
Expected: 89 tests pass, lint clean, build succeeds.

Then `pnpm dev` on `/` and confirm: the hero shows total P&L with its qualifier line directly beneath, the provisional warning is amber and still names the 50-trade floor, four stat tiles show expectancy / profit factor / max drawdown / avg bars held, the cost card names the break-even cost, R-multiples render, and the breakdown tables show bars behind the P&L numbers. Check `?source=all` and confirm the blend warning appears.

- [ ] **Step 10: Commit**

```bash
git add web/src/app/page.tsx web/src/components web/src/styles
git commit -m "Rebuild the overview around a hero stat and the unused metrics"
```

---

### Task 6: Signals

**Files:**
- Create: `web/src/components/Segmented.tsx`, `web/src/components/ConfidenceMeter.tsx`, `web/src/components/LevelScale.tsx`
- Modify: `web/src/components/FilterBar.tsx`, `web/src/components/SignalList.tsx`, `web/src/components/SignalRow.tsx`, `web/src/components/RationalePanel.tsx`, `web/src/components/VoteTable.tsx`, `web/src/components/ScopeNote.tsx`, `web/src/app/signals/page.tsx`, `web/src/styles/signals.css`, `web/src/styles/tables.css`

**Interfaces:**
- Consumes: `entryFraction` from `@/lib/levels`, `CONFIDENCE_THRESHOLD` from `@/lib/indicators`, `.segmented` CSS from Task 4.
- Produces: `LevelScale` (props `{ stop: number; entry: number; target: number; direction: Direction }`), reused by Task 7.

- [ ] **Step 1: Write `Segmented`**

`web/src/components/Segmented.tsx` — a button-based toggle reusing the `.segmented` classes the rail already defines:

```tsx
export interface SegmentedOption<T extends string> {
  value: T | undefined;
  label: string;
}

export interface SegmentedProps<T extends string> {
  options: SegmentedOption<T>[];
  value: T | undefined;
  onChange: (value: T | undefined) => void;
  label: string;
}

export default function Segmented<T extends string>({ options, value, onChange, label }: SegmentedProps<T>) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.label}
          type="button"
          className={`segmented-option${option.value === value ? " segmented-option-active" : ""}`}
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Write `ConfidenceMeter`**

`web/src/components/ConfidenceMeter.tsx` — the threshold marker is what makes this worth drawing rather than printing:

```tsx
import { CONFIDENCE_THRESHOLD } from "@/lib/indicators";
import { formatPercent } from "@/lib/format";

export interface ConfidenceMeterProps {
  confidence: number;
}

export default function ConfidenceMeter({ confidence }: ConfidenceMeterProps) {
  const cleared = confidence >= CONFIDENCE_THRESHOLD;

  return (
    <span className="meter" title={`Threshold ${formatPercent(CONFIDENCE_THRESHOLD)}`}>
      <span className="meter-track">
        <span
          className={`meter-fill${cleared ? " meter-fill-cleared" : ""}`}
          style={{ width: `${Math.min(100, Math.max(0, confidence * 100))}%` }}
        />
        <span className="meter-threshold" style={{ left: `${CONFIDENCE_THRESHOLD * 100}%` }} />
      </span>
      <span className="meter-value num">{formatPercent(confidence)}</span>
    </span>
  );
}
```

- [ ] **Step 3: Write `LevelScale`**

`web/src/components/LevelScale.tsx`. `entryFraction` is unclamped by design, so clamp here for the visual offset only, and say so when the value is out of range:

```tsx
import type { Direction } from "@/lib/types";
import { entryFraction } from "@/lib/levels";
import { formatPrice } from "@/lib/format";

export interface LevelScaleProps {
  stop: number;
  entry: number;
  target: number;
  direction: Direction;
}

export default function LevelScale({ stop, entry, target, direction }: LevelScaleProps) {
  const fraction = entryFraction(stop, entry, target);
  if (fraction === null) {
    return <p className="level-scale-empty">Stop and target are the same price.</p>;
  }

  const offset = Math.min(1, Math.max(0, fraction));
  const malformed = fraction < 0 || fraction > 1;

  return (
    <div className="level-scale">
      <div className="level-scale-track">
        <span className="level-scale-risk" style={{ width: `${offset * 100}%` }} />
        <span className="level-scale-entry" style={{ left: `${offset * 100}%` }} />
      </div>
      <div className="level-scale-labels">
        <span className="tone-negative num">{formatPrice(stop)}</span>
        <span className="num">{formatPrice(entry)}</span>
        <span className="tone-positive num">{formatPrice(target)}</span>
      </div>
      <p className="micro level-scale-legend">
        Stop · Entry · Target ({direction})
      </p>
      {malformed && (
        <p className="level-scale-warning">
          Entry sits outside its own stop and target. This level set is malformed.
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Turn the filter bar into a toolbar**

In `FilterBar.tsx`, replace the direction `<select>` with `Segmented`, keeping the other four fields:

```tsx
<div className="filter-field">
  <span className="micro">Direction</span>
  <Segmented
    label="Direction"
    value={criteria.direction}
    onChange={(direction) => onChange({ ...criteria, direction })}
    options={[
      { value: undefined, label: "Any" },
      { value: "LONG" as Direction, label: "Long" },
      { value: "SHORT" as Direction, label: "Short" },
      { value: "WAIT" as Direction, label: "Wait" },
    ]}
  />
</div>
```

The `DIRECTIONS` constant is now unused — delete it. Change the outer `<label className="filter-field">` wrappers to `<label className="filter-field"><span className="micro">…</span>` so every field label uses the same micro treatment.

- [ ] **Step 5: Turn signal rows into an aligned tape**

In `SignalRow.tsx`, replace the confidence `<span>` with `<ConfidenceMeter confidence={signal.confidence} />` and give the summary button fixed columns. In `web/src/styles/signals.css`, replace `.signal-row-summary`'s flex layout with a grid so the columns line up down the page:

```css
.signal-row-summary {
  display: grid;
  grid-template-columns: 4.5rem 4.5rem minmax(120px, 1fr) 6rem 12rem;
  align-items: center;
  gap: calc(var(--space) * 1.5);
  width: 100%;
  padding: calc(var(--space) * 1.25) calc(var(--space) * 2);
  background: none;
  border: none;
  color: var(--ink);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background-color 150ms;
}

.signal-row-summary:hover {
  background: var(--surface-2);
}

.signal-row-ticker {
  font-family: var(--font-mono);
  font-weight: 600;
}

.signal-row-timestamp {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--faint);
  text-align: right;
}
```

Delete the `margin-left: auto` from `.signal-row-timestamp` — the grid now places it. The outcome badge occupies the fourth column; when a signal has no trade the cell renders empty, which keeps every row's columns aligned. Update `SignalRow.tsx` to always emit that cell:

```tsx
<span className="signal-row-outcome">
  {outcome && <span className={`signal-badge ${outcomeClass(outcome)}`}>{outcome}</span>}
</span>
```

- [ ] **Step 6: Split the rationale panel into three columns**

In `RationalePanel.tsx`, wrap the three existing blocks in `<div className="rationale-columns">` and add the level scale inside the levels block, above the existing `<dl>`, only when the signal is actionable and all three prices exist:

```tsx
{signal.direction !== "WAIT" &&
  signal.entry !== null &&
  signal.stop !== null &&
  signal.target !== null && (
    <LevelScale
      stop={signal.stop}
      entry={signal.entry}
      target={signal.target}
      direction={signal.direction}
    />
  )}
```

Everything else in this component — the reasoning, the provenance line, the vote tally heading, the volume-modifier note, the WAIT stand-aside sentence, and the ATR arithmetic footnote — stays exactly as written.

```css
.rationale-columns {
  display: grid;
  grid-template-columns: 1.2fr 1.4fr 1fr;
  gap: calc(var(--space) * 3);
}

@media (max-width: 1100px) {
  .rationale-columns {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 7: Style the meter and the scale**

Add to `web/src/styles/signals.css`:

```css
.meter {
  display: flex;
  align-items: center;
  gap: var(--space);
}

.meter-track {
  position: relative;
  flex: 1;
  height: 5px;
  border-radius: 3px;
  background: var(--surface-2);
  overflow: hidden;
}

.meter-fill {
  display: block;
  height: 100%;
  background: var(--faint);
}

.meter-fill-cleared {
  background: var(--accent);
}

.meter-threshold {
  position: absolute;
  top: -2px;
  bottom: -2px;
  width: 1px;
  background: var(--line-strong);
}

.meter-value {
  font-size: 0.8rem;
  color: var(--muted);
  min-width: 3.5rem;
  text-align: right;
}

.level-scale-track {
  position: relative;
  height: 5px;
  border-radius: 3px;
  background: var(--win);
  margin-bottom: var(--space);
}

.level-scale-risk {
  position: absolute;
  inset: 0 auto 0 0;
  border-radius: 3px 0 0 3px;
  background: var(--loss);
}

.level-scale-entry {
  position: absolute;
  top: -4px;
  bottom: -4px;
  width: 2px;
  background: var(--ink);
}

.level-scale-labels {
  display: flex;
  justify-content: space-between;
  font-size: 0.8rem;
}

.level-scale-legend {
  margin-top: calc(var(--space) / 2);
}

.level-scale-warning {
  margin-top: var(--space);
  color: var(--caution);
  font-size: 0.8rem;
}

.level-scale-empty {
  color: var(--muted);
  font-size: 0.8rem;
}
```

- [ ] **Step 8: Update the page and `ScopeNote`**

Change `signals/page.tsx`'s `<main className="page-content">` to `<main className="canvas">`, and put the heading and count in a `.page-head`:

```tsx
<div className="page-head">
  <h1>Signals</h1>
  <span className="micro">{signals.length} signals</span>
</div>
```

In `ScopeNote.tsx`, change the wrapper class from `provenance-band` to `scope-note` and the paragraph to `micro`, then add to `web/src/styles/cards.css`:

```css
.scope-note {
  margin-bottom: calc(var(--space) * 3);
  padding-left: calc(var(--space) * 1.5);
  border-left: 2px solid var(--line-strong);
  max-width: 80ch;
}
```

Also restyle `.vote-table` in `tables.css` to match the new palette: `border-color: var(--line)`, header cells `color: var(--faint)` with the `.micro` letter-spacing, and vote cells in `var(--font-mono)`.

- [ ] **Step 9: Verify**

Run: `pnpm test && pnpm lint && pnpm build`
Expected: 89 tests pass, lint clean, build succeeds.

Then `pnpm dev` on `/signals` and confirm: rows align into columns down the page, confidence meters show the threshold tick with cleared signals in teal, the direction toggle filters, expanding a row shows three columns with the stop/entry/target scale, and the ATR footnote is still present. Expand a WAIT signal and confirm the stand-aside sentence shows and no scale is drawn.

- [ ] **Step 10: Commit**

```bash
git add web/src/components web/src/app/signals web/src/styles
git commit -m "Rebuild the signal list as an aligned tape with confidence meters"
```

---

### Task 7: Positions

**Files:**
- Create: `web/src/components/OpenPositions.tsx`, `web/src/components/PositionCard.tsx`
- Delete: `web/src/components/PositionsTable.tsx`
- Modify: `web/src/components/FillsTable.tsx`, `web/src/app/positions/page.tsx`, `web/src/styles/cards.css`, `web/src/styles/tables.css`

**Interfaces:**
- Consumes: `LevelScale` from Task 6, `shareOfMax` from `@/lib/scale`, `distanceToStop`/`distanceToTarget`/`isStale` from `@/lib/positions`.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write `PositionCard`**

`web/src/components/PositionCard.tsx`:

```tsx
import type { Trade } from "@/lib/types";
import { formatCurrency, formatTimestamp } from "@/lib/format";
import { distanceToStop, distanceToTarget } from "@/lib/positions";
import LevelScale from "@/components/LevelScale";

export interface PositionCardProps {
  position: Trade;
  stale: boolean;
}

export default function PositionCard({ position, stale }: PositionCardProps) {
  const toStop = distanceToStop(position);
  const toTarget = distanceToTarget(position);

  return (
    <article className="card position-card">
      <header className="position-card-head">
        <span className="position-card-ticker num">{position.ticker}</span>
        <span className={`signal-badge tone-${position.direction === "SHORT" ? "negative" : "positive"}`}>
          {position.direction}
        </span>
        {stale && <span className="positions-stale-badge">STALE</span>}
        <span className="micro position-card-age">{formatTimestamp(position.created_at)}</span>
      </header>

      <LevelScale
        stop={position.stop}
        entry={position.entry}
        target={position.target}
        direction={position.direction}
      />

      <dl className="pair-grid">
        <div>
          <dt className="micro">To stop</dt>
          <dd className="num tone-negative">{formatCurrency(toStop.dollars)}</dd>
        </div>
        <div>
          <dt className="micro">To target</dt>
          <dd className="num tone-positive">{formatCurrency(toTarget.dollars)}</dd>
        </div>
        <div>
          <dt className="micro">Shares</dt>
          <dd className="num">{position.shares}</dd>
        </div>
      </dl>
    </article>
  );
}
```

- [ ] **Step 2: Write `OpenPositions`**

`web/src/components/OpenPositions.tsx` replaces `PositionsTable.tsx`. The honesty note is carried across word for word:

```tsx
import type { Trade } from "@/lib/types";
import { isStale } from "@/lib/positions";
import PositionCard from "@/components/PositionCard";

export interface OpenPositionsProps {
  positions: Trade[];
  now: Date;
}

export default function OpenPositions({ positions, now }: OpenPositionsProps) {
  return (
    <section className="open-positions">
      <h2 className="micro">Open positions</h2>
      <p className="positions-note">
        No live price feed is wired into this dashboard. The columns below show distance to
        stop and distance to target as of entry — not current value or unrealized P&amp;L,
        which this app has no data to compute.
      </p>
      {positions.length === 0 ? (
        <p className="positions-empty">No open positions.</p>
      ) : (
        <div className="position-grid">
          {positions.map((position) => (
            <PositionCard
              key={position.id}
              position={position}
              stale={isStale(position.created_at, now)}
            />
          ))}
        </div>
      )}
    </section>
  );
}
```

Then `rm web/src/components/PositionsTable.tsx` and update the import in `positions/page.tsx`, changing `<PositionsTable positions={positions} now={now} />` to `<OpenPositions positions={positions} now={now} />` and `<main className="page-content">` to `<main className="canvas">` with a `.page-head` as in Task 6 Step 8.

- [ ] **Step 3: Add the P&L bar to the fills table**

In `FillsTable.tsx`, compute the shares once from the sorted rows — outside the JSX — and render the same `.cell-bar` treatment Task 5 added:

```tsx
const shares = shareOfMax(sorted.map((trade) => trade.pnl ?? 0));
```

```tsx
<td className={`pnl-cell num ${trade.pnl !== null && trade.pnl >= 0 ? "tone-positive" : "tone-negative"}`}>
  <span className="cell-bar" style={{ width: `${shares[index] * 100}%` }} aria-hidden="true" />
  <span className="cell-value">{formatCurrency(trade.pnl)}</span>
</td>
```

with the map changed to `sorted.map((trade, index) => ...)`. Add `import { shareOfMax } from "@/lib/scale";`.

- [ ] **Step 4: Style the position grid**

Add to `web/src/styles/cards.css`:

```css
.position-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: calc(var(--space) * 2);
}

.position-card-head {
  display: flex;
  align-items: center;
  gap: var(--space);
  margin-bottom: calc(var(--space) * 2);
}

.position-card-ticker {
  font-size: 1.1rem;
  font-weight: 600;
}

.position-card-age {
  margin-left: auto;
}

.positions-note {
  color: var(--caution);
  font-size: 0.85rem;
  max-width: 72ch;
  margin: var(--space) 0 calc(var(--space) * 2);
}
```

Update `.positions-stale-badge` to use `color: var(--caution); border-color: var(--caution);`.

In `tables.css`, retire the `.positions-table` selectors (the component is gone) and restyle `.fills-table` to the new palette: `border: 1px solid var(--line)`, `background: linear-gradient(to bottom, var(--surface-2), var(--surface))`, header cells `color: var(--faint)` with `.micro` letter-spacing, body cells in `var(--font-mono)` with `tabular-nums`, and every table wrapped so it can scroll:

```css
.table-scroll {
  overflow-x: auto;
  border-radius: var(--radius);
}
```

Wrap the `<table>` in `FillsTable.tsx` and `BreakdownTable.tsx` in `<div className="table-scroll">`.

- [ ] **Step 5: Verify**

Run: `pnpm test && pnpm lint && pnpm build`
Expected: 89 tests pass, lint clean, build succeeds.

Then `pnpm dev` on `/positions` and confirm: open positions render as cards with the stop/entry/target scale, the "no live price feed" note is present and amber, STALE badges show on positions older than 24h, and the fills table shows bars behind the P&L column. With no open positions, confirm "No open positions." renders.

- [ ] **Step 6: Commit**

```bash
git add web/src/components web/src/app/positions web/src/styles
git commit -m "Rebuild positions as cards with a stop-entry-target scale"
```

---

### Task 8: Sweep and verification

**Files:**
- Modify: `web/src/app/error.tsx`, `web/src/styles/*.css` (dead-rule removal)

**Interfaces:**
- Consumes: everything above.
- Produces: the finished redesign.

- [ ] **Step 1: Restyle the error boundary**

`error.tsx` keeps every word it has. Change `<main className="page-content">` to `<main className="canvas">` and give the retry button a real appearance — it currently inherits the browser default, which will look broken against the new palette. Add to `web/src/styles/shell.css`:

```css
.button {
  padding: calc(var(--space) * 0.75) calc(var(--space) * 2);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  color: var(--ink);
  font: inherit;
  cursor: pointer;
  transition: border-color 150ms, color 150ms;
}

.button:hover {
  border-color: var(--accent);
  color: var(--accent);
}
```

and set `className="button"` on the button, plus `margin-top: calc(var(--space) * 2)` via a wrapping `<p>`.

- [ ] **Step 2: Delete dead CSS**

Run `grep -rn "page-content\|provenance-band\|stat-tile-value-\|positions-table\|nav-link" web/src` and confirm zero hits in `.tsx` files. Delete every CSS rule whose selector no longer appears in any component. If a selector is still referenced, the corresponding task missed an update — fix the component, not the CSS.

- [ ] **Step 3: Re-run the contrast gate**

Re-run the checker from Task 2 Step 5 against the final `tokens.css` values. Every row must PASS on both columns. Additionally check `--caution` against `--surface-2` composited, since the positions note and provisional warning are small amber text on a card.

- [ ] **Step 4: Verify reduced motion**

Enable macOS System Settings → Accessibility → Display → Reduce motion. Reload all three pages. Confirm no transition or animation runs: hover a rail link, hover a signal row, and hover a position card.

- [ ] **Step 5: Verify responsive behavior**

At 1400px, 1100px, 900px and 480px viewport widths, confirm on all three pages: the page body never scrolls horizontally, the rail becomes a top bar below 900px, multi-column grids collapse to one column, and the fills and breakdown tables scroll inside their own containers rather than pushing the page wide.

- [ ] **Step 6: Full verification**

Run: `pnpm test && pnpm lint && pnpm build`
Expected: 89 tests pass, lint clean, build succeeds. Paste the actual output into the commit body — a summarized "all green" is not verification.

Then run the Flask API and `pnpm dev` together and walk all three routes under both `?source=live` and `?source=all`.

- [ ] **Step 7: Commit**

```bash
git add web/src
git commit -m "Restyle the error boundary and drop superseded CSS"
```

---

## Self-review notes

- **Spec coverage:** tokens/type/motion → Task 2; grid backdrop → Task 2; shell and scope threading → Task 4; overview IA including all nine previously-unused metrics fields → Task 5; signals tape, segmented control, confidence meter, three-column rationale → Task 6; position cards and fills bars → Task 7; responsive, reduced motion, contrast, empty states, protected copy → Tasks 2, 5, 6, 7, 8.
- **One deliberate deviation from the spec**, called out inline in Task 4: the rail's scope block omits counts, because sourcing them would reintroduce the duplicate `getMetrics` fetch that commit `74a50f4` deleted. Counts live in each page header instead.
- **Naming is consistent across tasks:** `entryFraction`, `shareOfMax`, `breakdownRows`, `breakEvenCost`, `CONFIDENCE_THRESHOLD`, `LevelScale`, `ConfidenceMeter`, `Segmented`, `RatioBar`, `HeroStat`, `WinLossCard`, `RMultipleCard`, `OpenPositions`, `PositionCard`.
- **Test count moves 74 → 89 in Task 3** and holds there; Tasks 4–8 add no tests because they add no domain logic, which is the intended split.

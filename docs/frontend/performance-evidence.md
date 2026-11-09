# Frontend performance measurements

Issue #152, implemented with `claude-opus-5-5` (provider-default effort) on 2026-11-08.

## How to measure

From `web/`, after `pnpm build`:

```bash
pnpm test:performance
```

This runs `e2e/performance.spec.ts` twice against the production server, once per fixture, in desktop Chromium with 4x CPU throttling. Results land in `web/performance-results/{small,large}.json` (gitignored). The run takes about six minutes, mostly because each route is watched for 31 seconds of background traffic.

- **Small fixture**: the usual synthetic browser fixture. No live closed trades, so the default overview shows no chart; `/?source=all` draws a 29-point chart from backtest rows.
- **Large fixture** (`PERF_FIXTURE=large`): adds 5,000 live closed trades and their signals, about a year of intraday trading. This grows the overview's equity curve and table. Signals (50 per page) and position-state closed trades (50) are already capped by the API, so those routes barely change.

For each of overview, overview with all sources, positions, signals and an active (queued) replay run, the spec records: document and script bytes (compressed transfer size), Recharts script bytes, time until the chart is visible, FCP, LCP, total blocking time from long tasks, DOM node count, and every fetch made during a 31-second idle window after load, split into route refreshes, link prefetches and API polls.

## What the baseline showed

Before (commit `46678cc`) and after, both at 4x CPU throttling:

| Route, fixture | Script KB | Doc KB | Blocking ms | DOM nodes | Chart visible ms | Background requests / 31 s |
|---|---|---|---|---|---|---|
| `/` small | 248 → 138 | 8.7 → 8.6 | 25 → 20 | 215 → 211 | no chart | 20 → 6 |
| `/?source=all` small | 248 → 239 | 10.5 → 10.1 | 124 → 83 | 473 → 376 | 659 → 617 | 20 → 6 |
| `/` large | 248 → 239 | 86 → 50 | 1,149 → 472 | 15,428 → 420 | 2,820 → 1,088 | 20 → 6 |
| `/positions` large | 144 → 139 | 2.8 → 2.8 | 16 → 21 | 756 → 754 | no chart | 10 → 10 |
| `/signals` large | 150 → 139 | 8.9 → 8.9 | 20 → 17 | 824 → 821 | no chart | 20 → 6 |
| `/runs/<id>` active | 147 → 136 | 8.4 → 8.4 | 0 → 0 | 177 → 174 | no chart | 94 → 14 |

Raw results: [before](evidence/issue-152-performance-before-2026-11-08.json), [small after](evidence/issue-152-performance-small-after-2026-11-08.json), [large after](evidence/issue-152-performance-large-after-2026-11-08.json).

Three bottlenecks showed up in the numbers:

1. **Link prefetches after every refresh.** All these routes are dynamic, and Next doesn't cache dynamic prefetches (`staleTimes.dynamic` is off). So every `router.refresh()` made each visible `<Link>` prefetch again. The side rail alone has ten. On an active run, which refreshes every 3 seconds, that came to 94 requests in 31 seconds, where 10 refreshes and 4 status polls were the intent.
2. **The equity table in the DOM.** The overview rendered one table row per closed trade inside the closed "View equity data" disclosure. At 5,000 trades that's about 15,000 DOM nodes and over a second of blocking time.
3. **Recharts on every overview load.** The chart code (about 100 KB compressed) shipped with the overview even when there was nothing to plot, which is the default live view in the small fixture.

## What changed

- Side-rail links, the page-header back link and the provenance scope links now prefetch on hover, focus or touch (`IntentPrefetchLink`, following the hover-prefetch pattern in Next's prefetching guide) instead of whenever they're visible. Navigation still gets a prefetch before nearly every click, and keyboard users get one on focus. What remains in the background is only the intended polling.
- The equity table renders its rows the first time the disclosure opens. Exact values, the caption and the keyboard/axe checks in the accessibility suite are unchanged.
- The Recharts chart is its own client module loaded with `next/dynamic` (`ssr: false`). `ResponsiveContainer` never rendered on the server anyway, since it needs a measured width. A fixed-height slot keeps the layout from shifting while it loads.

Not changed, and why:

- **The chart still plots all 5,000 points.** The remaining 472 ms of blocking time on the large overview is mostly Recharts drawing and hydrating that curve. Downsampling would change what the chart shows and how arrow keys step through it, and 4x-throttled blocking time under 500 ms didn't seem worth it. Revisit if real journals get much bigger.
- **No virtualization or client cache library.** Signals and position state are bounded by the API, and once the table rows were deferred nothing else needed one.
- **Polling intervals are the same.** Freshness behavior (15 s refreshes, 5 s position state, 3 s active run) is untouched.

## Regression budgets

`e2e/performance.spec.ts` fails if any measured route goes over:

| | Small | Large |
|---|---|---|
| Script bytes | 260,000 | 260,000 |
| Document bytes | 20,000 | 64,000 |
| Total blocking time | 200 ms | 700 ms |
| DOM nodes | 1,200 | 1,200 |

It also fails if a route with no chart downloads Recharts, or if background requests in the 31-second window exceed the intended polls plus two (overview 8, positions 12, signals 8, active run 16). Prefetch amplification adds at least seven requests per refresh, so the slack can't hide it. Byte budgets sit about 10–25% above the measurements. Timing budgets have more room because blocking time varies between runs.

## Verification

- Frontend unit tests (71 files, 522 tests), ESLint, style lint, typecheck, Prettier and the production build passed.
- Full browser suite: 64 passed, including the chart keyboard/tooltip test, the exact-data disclosure with axe, reduced-motion checks and narrow layouts.
- Performance gate: small and large fixtures both passed.
- Ruff lint and format on `e2e/serve_sample_api.py`, and `git diff --check`, passed.

These measurements come from a single machine with throttled Chromium on localhost. They're good for spotting regressions between commits, not for predicting real-device numbers. Firefox and mobile emulation aren't measured. Two gate runs during development timed out because the Mac went into system sleep mid-run (`pmset -g log` showed a 902-second sleep matching the 914-second hang). On macOS, run the gate under `caffeinate -i` so timers aren't paused.

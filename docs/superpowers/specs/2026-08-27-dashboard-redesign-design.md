# Dashboard Redesign — "Instrument" — Design

Date: 2026-08-27
Status: approved for planning

## Goal

Give the Next.js dashboard a deliberate visual identity and a denser information
architecture. Two audiences, unchanged from the build spec: personal research use, and a
portfolio piece.

The reference is the design language of peterramos.dev — a sibling, not a copy. It shares
the lineage (committed dark ground, translucent hairline surfaces, a luminous accent, mono
micro-labels) and diverges everywhere the job differs: this is an instrument panel, not a
marketing page.

Nothing behind the API changes. The Flask endpoints, the signal engine, and
`analytics/metrics.py` are untouched.

## Constraint that shapes everything

This project's editorial position is that the measured edge sits below realistic
transaction costs, and that no conclusion should be drawn below 50 closed trades. A glowing
hero P&L with no qualifier would undercut that.

So caution is a first-class channel in the palette, not an afterthought. The provisional
warning, the backtest-blend warning, and STALE badges carry amber weight, and the hero stat
carries its qualifier on the line directly beneath it rather than in a box further down the
page. Eye-catching and honest are not in tension here as long as the caveat travels with
the number.

## Design language

| | Aperture (portfolio) | Instrument (this) |
|---|---|---|
| Geometry | `rounded-2xl`, airy | 10px radii, 8px spacing rhythm, dense |
| Backdrop | three soft radial blooms | fine grid field fading out + one low anchored glow |
| Display face | Sora | Space Grotesk |
| Numerals | display font | IBM Plex Mono, `tabular-nums`, everywhere a number appears |
| Second accent | violet, decorative | amber, functional (caution) |
| Canvas | 1024px | 1400px |

### Tokens

```css
--ground:      #04060B;
--surface:     rgba(150, 180, 255, 0.05);
--surface-2:   rgba(150, 180, 255, 0.08);
--line:        rgba(150, 180, 255, 0.13);
--line-strong: rgba(150, 180, 255, 0.26);
--ink:         #E9EFFA;
--muted:       #91A0BA;
--faint:       #77859F;

--accent:      #35E8D2;   /* structural only: links, focus, active nav, chart line */
--caution:     #FFB454;   /* provisional, backtest blend, stale */
--win:         #4ADE80;   /* money and direction only */
--loss:        #FF6B6B;
```

The teal/mint split is deliberate. Teal never encodes a number's sign; mint and coral never
appear on chrome. This keeps "this control is interactive" and "this trade made money" from
competing for the same reading.

Every foreground value must clear WCAG AA against `--ground` and against the composited
translucent surface. Verify before shipping, the way the portfolio's palette was verified.

### Type

Three faces via `next/font/google`, replacing Geist:

- **Space Grotesk** — headings, `letter-spacing: -0.03em`
- **IBM Plex Sans** — prose
- **IBM Plex Mono** — all numerals, plus uppercase micro-labels at `0.18em`

### Motion

Restrained by intent: hover lift on cards, 150ms color transitions, a slow pulse on the
live dot, one draw-in on the equity curve. No parallax, no animated background.
`prefers-reduced-motion: reduce` disables all of it.

## Information architecture

### Shell

A 200px left rail: wordmark, three nav items, and a scope block at the bottom showing the
active source with counts. Content capped at 1400px. Below 900px the rail becomes a top
bar. No other persistent chrome — each page opens with its own header row.

### Overview

Twelve-column grid. Every value comes from the existing `/api/metrics` response. The
figures in the sketch below are illustrative placeholders for layout only — the live
sample is currently well under the 50-trade floor and its P&L is negative.

```
● LIVE
+$1,284.50                          <- Plex Mono, ~64px, mint/coral
2,514 closed · 36.2% win · ⚠ provisional below 50

┌──────────────────────────────┬─────────────────────┐
│ equity curve                 │ WIN / LOSS ratio bar│
│ teal line, area gradient     │ avg win / avg loss  │
└──────────────────────────────┴─────────────────────┘
┌──────────┬──────────┬──────────┬──────────┐
│expectancy│ profit   │ max DD   │ avg bars │
│          │ factor   │          │ held     │
└──────────┴──────────┴──────────┴──────────┘
┌──────────────────────────────┬─────────────────────┐
│ cost-adjusted expectancy     │ R-MULTIPLES         │
│ net crosses $0 at $3.05      │ avg / win / loss    │
└──────────────────────────────┴─────────────────────┘
┌──────────────────────────────┬─────────────────────┐
│ by regime (inline bars)      │ by ticker           │
└──────────────────────────────┴─────────────────────┘
```

`profit_factor`, `avg_win`, `avg_loss`, `avg_r_multiple`, `avg_win_r`, `avg_loss_r`,
`avg_bars_held`, `n_wins` and `n_losses` are all already returned by the API and currently
discarded by the UI. This layout consumes them. No new endpoint, no new query.

The break-even readout is `breakEvenCost(grossExpectancy) === grossExpectancy` — the cost
per trade at which net expectancy reaches zero. Trivial arithmetic, but it states the
project's central finding as a number instead of a paragraph.

### Signals

The list becomes a tape. Filters collapse into one toolbar; direction becomes a three-way
segmented control rather than a `<select>`. Each row is a fixed grid so columns align down
the page, and confidence renders as a meter with the 0.62 threshold marked.

Expanded detail splits three ways at width: reasoning + provenance | vote table | levels.
Entry, stop and target draw on a `stop ←|→ target` scale. The ATR arithmetic stays as a
mono footnote — it is the thing that makes the stop legible, and it should not be cut for
visual tidiness.

### Positions

Open positions become cards; there are few of them, and each has room for the level scale,
age, and a STALE badge. Recent fills stays a dense table with an inline bar in the P&L
column.

The "no live price feed is wired into this dashboard" note keeps its current wording and
gains caution styling. The columns still show distance to stop and target as of entry, and
must not be relabelled as unrealized P&L.

### Scope control

`?source=live|all` moves from an inline link on Overview into the rail and is honored by
all three pages. `/signals` and `/positions` currently hardcode `source=live`; they will
read the search param instead. This is a behavior change, approved: those pages will show
backtest rows when the scope is set to `all`, with the same blend warning Overview carries.

### Responsive

Rail collapses to a top bar under 900px. Multi-column grids collapse to one column. Every
table sits in an `overflow-x: auto` wrapper so the page body never scrolls horizontally.

## Components

New:

| Component | Responsibility |
|---|---|
| `SideRail` | Nav, wordmark, scope block |
| `HeroStat` | Headline figure with its qualifier line |
| `ConfidenceMeter` | Confidence bar with threshold marker |
| `LevelScale` | stop / entry / target on one axis |
| `RatioBar` | Two-part proportion bar |
| `Segmented` | Three-way toggle for direction |

Restyled in place: `Nav` (becomes `SideRail`), `StatTile`, `ProvenanceBand`, `ScopeNote`,
`EquityCurve`, `CostAdjustedExpectancy`, `BreakdownTable`, `FilterBar`, `SignalList`,
`SignalRow`, `RationalePanel`, `VoteTable`, `PositionsTable`, `FillsTable`, `error.tsx`.

Components stay presentational: props in, markup out. New derived values are pure functions
in `lib/`, not computed in JSX.

New logic in `lib/`, each with vitest coverage:

- `breakEvenCost(grossExpectancy)` in `lib/costs.ts`
- a level-scale position helper (entry's fractional position between stop and target)

## Styling approach

No Tailwind. The existing plain-CSS setup works, and converting every `className` would be
a large mechanical diff for no functional gain.

`globals.css` is already 543 lines and this roughly doubles it, so it splits into
`src/styles/` — `tokens.css`, `base.css`, `shell.css`, `cards.css`, `tables.css`,
`signals.css` — imported from `globals.css`. Plain CSS files, no new dependency, no build
change.

Recharts stays. The equity curve is restyled through props plus a gradient `defs` area
fill; it is not replaced with hand-rolled SVG.

## Error handling

`error.tsx` keeps its current job — the API being unreachable is the expected failure, and
the boundary must keep saying so plainly rather than showing an empty styled shell. It gets
the new palette and nothing else.

Empty states (`no open positions`, `no signals match these filters`, `not enough closed
trades to plot`) are restyled, not removed. A dashboard with no data should look
deliberate, not broken.

## Testing

- The existing 74 tests across 6 files must still pass. Baseline confirmed before starting.
- New `lib/` functions get their own tests, following the existing table-driven style.
- `pnpm lint` and `pnpm build` must both be clean.
- Visual verification: run the app against the live Flask API and check Overview, Signals
  (collapsed and expanded), and Positions at wide and narrow widths.

No component-mounting tests. Domain logic is testable without a DOM, which is the point of
keeping it in `lib/`.

## Out of scope

- Any change to the Flask API, the signal engine, or `analytics/metrics.py`
- A live price feed, and therefore unrealized P&L
- Light theme. This is a committed dark design, like its sibling.
- Vercel deployment, still blocked on SQLite locality

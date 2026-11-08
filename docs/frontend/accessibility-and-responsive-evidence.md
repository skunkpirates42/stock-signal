# Accessibility and responsive verification

Issue #150, verified locally on 2026-11-07 using gpt-6.1-sol with high reasoning. The application remains paper-only; no execution, accounting, strategy or provenance rules changed.

## Reproduce

From `web/`, install the locked dependencies and Playwright Chromium/Firefox, build with `pnpm build`, then run `pnpm test:browser`. The Playwright configuration starts the isolated sample Flask API and the production Next server. Browser requests are restricted to localhost. The zoom test uses an ephemeral local Chromium extension and its own temporary browser profile; it never modifies a user's browser profile. No broker orders or paid explanations are requested.

`pnpm test:accessibility` runs the accessibility, keyboard and browser-zoom subset. `pnpm test:smoke` and `pnpm test:interactions` remain available for focused Chromium checks. CI runs the combined browser suite once and uploads `playwright-report/` and `test-results/` on success or failure, preserving one complete report for seven days. HTML attachments include axe reports, screenshots, contrast samples and motion/zoom measurements. The JSON report is `web/test-results/results.json`.

The checked-in [measurement summary](evidence/issue-150-browser-checks-2026-11-07.json) was extracted from the successful combined report. Generated browser reports are ignored by Git, ESLint and Prettier.

## Results

| Check                                             | Result                                                                                                    |
| ------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Full frontend unit suite                          | 68 files, 489 tests passed                                                                                |
| Production build                                  | Passed                                                                                                    |
| ESLint, Next type generation/TypeScript, Prettier | Passed                                                                                                    |
| Combined browser suite                            | 62 passed; zero failures, skips or retries                                                                |
| Desktop Chromium 158.0.8127.18                    | 30 passed, including existing page smoke, signal search, replay queue/cancel and position freshness flows |
| Pixel 7 emulation, Chromium 158.0.8127.18         | 16 selected accessibility/keyboard checks passed                                                          |
| Desktop Firefox 159.0                             | 16 selected accessibility/keyboard checks passed                                                          |
| `git diff --check`                                | Passed                                                                                                    |

Axe checks WCAG 2 A/AA, 2.1 AA and 2.2 AA tags on `/`, `/?source=all`, `/signals`, `/positions`, `/run`, `/runs`, `/research` and `/system` in all three projects: 24 route scans with zero violations. Six additional scans assert the expanded equity-data and metric-definition states. Axe's incomplete results remain in the raw reports; a zero-violation result is not a complete accessibility certification.

## Findings and fixes

| Finding                                                                                                               | Fix and evidence                                                                                                                                                                                                                                                                                                                |
| --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Most tables had no accessible name; scroll wrappers were not consistently keyboard reachable across engines.          | `DataTable` now requires a caption, renders it as a native visually hidden caption, and provides a named, focusable scroll region. Migrated breakdown, fills, votes, research comparison and system examples. Browser assertions inspect accessible table names and use ArrowRight to scroll an intentionally long table value. |
| Chart values depended on a visual tooltip and its hidden prose summary.                                               | Equity has a named keyboard-accessible Recharts application, a visible summary and a native disclosure containing every equity value with its UTC label. Tab and arrow keys expose changing tooltip values; Enter/Space open and close the exact-data table.                                                                    |
| The signal summary's outer focus outline was clipped by its parent.                                                   | Its focus outline is inset. A 320px keyboard flow checks focus style and expansion; the screenshot shows the complete accent ring.                                                                                                                                                                                              |
| The mobile rail did not wrap; grid minimums and long figures could exceed narrow content widths.                      | Rail/navigation wrap, grid tracks can shrink, position cards fit their container, and long figures can wrap. Six pages are exercised at 320 CSS pixels, including an injected long currency value and a long table identifier.                                                                                                  |
| Actual 400% browser zoom exposed replay form expansion around the saved dataset SHA.                                  | The form uses a shrinking grid track and card notes wrap long unbroken content. All form controls remain inside the viewport at 200% and 400%. The complete SHA remains visible in the narrow-page screenshot.                                                                                                                  |
| Focusing a metric below the mobile fold could immediately hide its definition when the browser scrolled it into view. | Focused definitions are repositioned on scroll/resize. Escape, blur and outside pointer still dismiss. The mobile regression now tabs to the definition, scrolls while focused, checks visibility and captures the unclipped panel and focus ring.                                                                              |
| Axe found provenance links distinguishable from surrounding text only by color (2.41:1 link-to-text contrast).        | Prose links now have a persistent underline. The route scans pass after the fix.                                                                                                                                                                                                                                                |

## Independent review follow-up

Independent standards review reported no actionable findings. Specification review found that the new equity table used a price formatter that removed negative signs. Sign-preserving balance formatters now keep the table, summary, tooltip and axis consistent. A negative-equity component regression and formatter/summary tests passed (46 focused tests); lint, typecheck, formatting and `git diff --check` passed after the correction. The specification reviewer independently confirmed the finding resolved. The original 489-unit/62-browser results above precede this formatting correction. Human-operated interaction testing remains outside the recorded coverage.

## Rendered contrast

The browser records each sampled element's computed foreground, temporarily hides its text while disabling color transitions, and screenshots that element. PNG pixels at nine interior positions provide the actual composited background, including translucent card/rail layers, gradients and the page grid/glow. Ratios use the WCAG sRGB luminance calculation. Disabling the temporary color transition prevents text fading into the background measurement; it does not alter the background surface.

Samples cover active rail links, stat labels, card notes, table headers, positive figures, signal timestamps, filter labels and active segmented controls. Every sampled ratio meets the 4.5:1 small-text threshold. The lowest ratio was 4.948:1 in desktop/mobile Chromium and 4.944:1 in Firefox, on table-header surfaces. Individual values and background images are in the report; the summary preserves numeric measurements. This is representative rendered-surface coverage, not an assertion about every possible pixel/state.

## Recharts reduced motion and browser zoom

Recharts 3.10.1's `isAnimationActive="auto"` uses its JavaScript media-query listener. Both the area and tooltip explicitly retain this mode. A mutation observer installed before application JavaScript counts reveal-rectangle width updates across the full initial animation interval, while also asserting that the final curve exists. Under `prefers-reduced-motion: reduce`, updates were **0** in all three projects. The normal-motion controls recorded **90**, **90** and **152** updates in desktop Chromium, mobile Chromium and Firefox respectively. This directly observes the JavaScript-driven SVG reveal, beyond the existing CSS motion overrides. Live preference changes and every tooltip transition are not covered by that measurement.

The Chromium-only zoom test calls `chrome.tabs.setZoom` at 200% and 400% in a native browser viewport. It verifies the browser-reported zoom and independently measures layout width and device pixel ratio:

| Browser zoom | `innerWidth` | `devicePixelRatio` |
| ------------ | ------------ | ------------------ |
| 100%         | 1280         | 1                  |
| 200%         | 640          | 2                  |
| 400%         | 320          | 4                  |

It checks overview long figures, navigation, replay controls, signal controls and positions at each zoom. This is browser zoom with layout reflow; no CSS transform, CSS zoom or pinch/page-scale emulation is used. Zoom screenshots use native CDP capture because Playwright's emulated screenshot dimensions can crop a browser-zoomed viewport.

## Focused visual review and limits

The implementing agent visually inspected screenshots from the successful run, separately from the scripted assertions:

- Chromium at 320px: long overview currency wraps with all digits present; stacked cards and table columns remain readable; primary navigation and scope links remain visible.
- Chromium and Firefox at 320px: replay fields fit the card, the saved SHA wraps completely, and the queue control is visible. Native selects shorten long selected labels visually; their full option text remains available in the native chooser.
- Chromium at 320px: signal filters fit, the expanded SHORT row has a complete focus outline, reasoning/provenance and missing-value explanations remain visible.
- Pixel 7 screenshot: the metric's focus ring and definition/formula are visible above the card clipping boundary and within the viewport.
- Actual Chromium 400% screenshot: primary navigation and scope controls wrap within the browser viewport. The rail is in normal document flow, allowing scrolling to content.

These were agent visual checks of captured browser output. Keyboard actions were scripted, not human-operated manual testing. No VoiceOver/NVDA/JAWS session, physical mobile device, WebKit, forced-colors mode or operating-system text-only enlargement was tested. Firefox/mobile execute the selected subset; browser zoom is Chromium-only. The sample API's research index is empty and its seeded expanded DEEP signal has no votes, so populated saved-research details and every possible data-dependent table state were not browser-audited. Existing unit tests and the caption migration cover those interfaces but do not replace future assistive-technology checks.

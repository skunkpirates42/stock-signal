# Scoped styles and CSS-aware checks

Issue #151, implemented with `gpt-6.1-sol` at medium reasoning on 2026-11-08.

Research detail, replay controls/run history, and design-system styles now use CSS Modules. Shared card surfaces, typography, colors, spacing tokens, and UI primitives retain their existing global rules. Button keeps its existing inline flag. Remaining global feature styles can migrate when their components are next touched.

`pnpm lint` includes `pnpm lint:styles`. The checker uses css-tree to parse declarations and values in every stylesheet under `web/src`, including modules. It enforces color literals, defined type-scale tokens, spacing tokens, and radius tokens without confusing comments, quoted content, selectors, or URLs with declarations. Parser regressions cover nested arithmetic, literal fallbacks, modern colors, malformed CSS, and the narrowly scoped screen-reader margin exception. Token contrast tests live separately in `contrast.test.ts`; rendered contrast checks remain in the browser suite.

## Verification

- Full frontend unit suite: 71 files, 521 tests passed.
- ESLint, CSS token lint, typecheck, production build, and Prettier passed.
- Python browser fixture: Ruff lint/format and compilation passed.
- `git diff --check` passed.
- Full browser suite: 64 passed, zero failures, skips or retries; [recorded results](evidence/issue-151-browser-checks-2026-11-08.json).

Run `pnpm build` followed by `pnpm test:browser` from `web/`. The harness uses temporary local databases and synthetic artifacts, and restricts browser requests to localhost. It exercises desktop Chromium, Pixel 7 emulation, and desktop Firefox. Existing checks cover route rendering, keyboard operation, contrast, narrow layouts, and browser zoom. New Chromium checks visit populated research details at 1280px and 320px, expand reproducibility, assert configuration/artifact grid styling and no horizontal overflow, then navigate through the system page and back to research to exercise stylesheet loading.

The coordinator inspected both research screenshots: configuration values and long artifact hashes wrap; artifact groups have two columns on desktop and one on mobile. Screenshots and full reports remain in ignored `web/test-results` and `web/playwright-report`; CI uploads browser artifacts. These checks are representative cascade coverage, not exhaustive screenshot comparison or human assistive-technology testing. Synthetic research diagnostics are unavailable in the fixture, so populated audit-count maps are not visually covered.

## Navigation capture correction

The first desktop full-page screenshot made the navigation appear to float midway down the document. A failing capture precondition reproduced the cause: opening Reproducibility scrolled the page to 1124px before capture. Measurements confirmed that the desktop sticky rail remained at viewport x=0, y=0, width=200, height=900 both before and after scrolling. Mobile navigation was correctly static and scrolled with the document.

The test now records top/scrolled rail geometry, captures the scrolled viewport, returns to scrollY=0, verifies the original geometry, and captures both top viewport and full-page evidence. Both focused cases passed; [measurements](evidence/issue-151-nav-capture-checks-2026-11-08.json) preserve the diagnosis. No navigation CSS changed. These two checks ran after the complete 64-test suite above.

## Independent review

Separate standards and specification reviewers found no actionable issues in commit `5511118`. A nonblocking inherited checker limitation remains: an unquoted identifier such as `animation-name: red` is treated as a color literal, although no current stylesheet uses that pattern.

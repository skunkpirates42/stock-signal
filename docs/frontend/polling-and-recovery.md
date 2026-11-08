# Polling ownership and error recovery

Implemented for issue #148. Paper execution and deterministic trade rules are unchanged.

## Owners

| Resource                                 | Owner                                                          | Visible cadence                                                                  | Update                                                                                                                                                  |
| ---------------------------------------- | -------------------------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Operational health                       | `LiveStatus` → `/api/operational-status` → Flask `/api/status` | Immediately, then 15 seconds after each request settles                          | Parsed client state; no route refresh                                                                                                                   |
| Market clock                             | `LiveStatus` → `/api/market-status`                            | Immediately, then 15 seconds after each request settles                          | Parsed client state; no route refresh                                                                                                                   |
| Position/account observations            | `PositionsView` → `/api/position-state`                        | Immediately, then 5 seconds after each request settles                           | Last known positions plus availability/staleness warnings                                                                                               |
| Position price marks                     | `OpenPositions` → `/api/position-prices`                       | Immediately when live positions exist, then 5 seconds after each request settles | Last known marks with independent price warnings                                                                                                        |
| Overview metrics                         | Page-local `ServerDataRefresh`                                 | 15 seconds                                                                       | Route refresh; metrics remain server rendered and respect source/date filters                                                                           |
| Signal search                            | Page-local `ServerDataRefresh`                                 | 15 seconds                                                                       | Route refresh; query/filter state stays in the URL                                                                                                      |
| Run history and research index           | Page-local `ServerDataRefresh` on each page                    | 15 seconds                                                                       | Route refresh to discover changes/new results                                                                                                           |
| Active run detail                        | `JobActions` via `useRouteRefresh`                             | 3 seconds while queued/running/cancel requested                                  | Route refresh for server-rendered status, published results and artifacts; successful cancellation requests an immediate refresh through the same owner |
| Terminal run detail, saved result detail | Navigation/retry                                               | No automatic refresh                                                             | Completed records are snapshots; revisiting fetches the saved record                                                                                    |
| New-run catalog                          | Navigation/retry                                               | No automatic refresh                                                             | Catalog loaded on entry; queue endpoint validates submitted choices against current approved data                                                       |
| Design-system page                       | Static content                                                 | No route refresh                                                                 | Shared health status still polls independently                                                                                                          |

Each mounted page has at most one automatic route-refresh owner. The layout status owner never refreshes a route. Server-data owners wait one interval after mounting because navigation already fetched the page; returning from a hidden tab refreshes immediately. Transitions suppress overlapping route refresh requests, including cancellation-triggered refreshes. When the run becomes terminal, its owner stops. A route error unmounts the page's owner; the surviving layout polls cannot produce an automatic error/retry loop. The retry button delegates recovery to Next's `retry()` callback.

All pollers stop scheduling while hidden, resume on visibility, remove listeners and timers on unmount, and avoid overlapping their own data requests. Data polls abort on unmount and have an explicit 10-second deadline covering both fetch and body parsing. A stalled body releases the polling loop even if a mocked or noncompliant transport ignores abort. Failed data polls retain the last good value and mark it unavailable/stale; successful later polls clear the failure flag. Position freshness clocks and warnings retain their existing behavior. Server reads continue to use their existing bounded upstream timeouts.

## Failure records

The route and root-layout fallbacks use neutral load-failure wording. They never claim that an arbitrary rendering/schema failure proves Flask connectivity trouble, and never display the raw exception message.

`web_failure` console records contain only a fixed resource name, a category (`transport`, `http`, `timeout`, `aborted`, `schema`, `json`, or `unexpected`), and an optional Next error digest. References must be 1–80 ASCII letters, digits, underscores or hyphens; unsafe values are omitted. Records omit exception messages, stacks, causes, request URLs/query strings, headers, credentials, account data and response bodies. Cancellation during unmount is not recorded as a failed poll. Error-boundary records are emitted when the error changes, rather than on each render.

The operational-status route records its server-side failure category before returning a generic 503. Client polling records HTTP failure in that case; it cannot infer the upstream cause. Next production server-rendering errors may arrive with only a digest and a redacted error; those are honestly categorized `unexpected`. Match the safe reference with existing server diagnostics when available. These records are local console diagnostics, not hosted telemetry or an external logging integration.

## Request-count evidence

Method: deterministic component integration test with Vitest/jsdom fake timers, successful immediate synthetic responses, visible document, no Strict Mode double mount, interval `[0, 60 seconds]` inclusive. Components are mounted together as on each page: `LiveStatus`, the actual positions components (one live local-simulation position), and/or `JobActions`; the after-overview case mounts its new `ServerDataRefresh`. React transitions are flushed between seconds. The initial server navigation, asset requests and prefetches are excluded.

Baseline was measured against the unmodified components at commit `8b9d290f3c00edb103726eb84178986716a2f050`, before implementation. The test counted the old operational-status Server Action invocation as one request and intercepted `router.refresh()` calls. After measurements count the new status GET instead. The table measures request initiations, not a browser HAR or actual Flask/network traffic: Next may coalesce simultaneous route refresh calls. Upstream reads and route-response byte sizes were not measured. No production latency or backend-load claim follows from these counts.

| Page       | Status requests, before → after | Market requests | Position-state requests | Price requests | Route refresh initiations, before → after | Total initiations, before → after |
| ---------- | ------------------------------- | --------------- | ----------------------- | -------------- | ----------------------------------------- | --------------------------------- |
| Overview   | 5 → 5                           | 5 → 5           | 0 → 0                   | 0 → 0          | 5 → 4                                     | 15 → 14                           |
| Positions  | 5 → 5                           | 5 → 5           | 13 → 13                 | 13 → 13        | 5 → 0                                     | 41 → 36                           |
| Active run | 5 → 5                           | 5 → 5           | 0 → 0                   | 0 → 0          | 26 → 20                                   | 36 → 30                           |

The overview reduction removes the redundant mount refresh. Positions retain both five-second data pollers while removing all route refreshes. Active runs retain the three-second cadence while removing five layout-triggered refreshes and one redundant mount refresh.

Reproduce the after measurements from `web/`:

```sh
./node_modules/.bin/vitest run src/components/PollingOwnership.test.tsx --disableConsoleIntercept
```

The same test asserts the counts, status failure/recovery without route refresh, hidden-tab pause/resume, unmount cleanup, pending-transition suppression and manual error recovery. Existing position tests cover last-known holdings/marks and recovery; run-action tests cover cancel retry, terminal-state stopping and published results. `polledResource.test.ts` covers schema recovery and a stalled response body deadline. Operational-status route and fallback tests assert sanitized categories and references without raw sensitive details.

Verification uses installed local binaries because the workspace `pnpm` launcher attempts to bootstrap pinned pnpm 10.33.0 from the registry and fails on its network/signature lookup. This does not change the package manager declaration or lockfile.

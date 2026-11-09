import { mkdirSync, writeFileSync } from "node:fs";
import type { Page, Request } from "@playwright/test";
import { expect, test } from "./fixtures";

const fixture = process.env.PERF_FIXTURE ?? "small";
const CPU_SLOWDOWN = 4;
const BACKGROUND_WINDOW_MS = 31_000;

interface RouteMeasurement {
  route: string;
  documentBytes: number;
  scriptBytes: number;
  scriptRequests: number;
  chartScriptBytes: number;
  chartRendered: boolean;
  chartVisibleMs: number | null;
  firstContentfulPaintMs: number | null;
  largestContentfulPaintMs: number | null;
  totalBlockingTimeMs: number;
  domNodes: number;
  backgroundRequests: Record<string, number>;
}

// Headroom over the optimized measurements in docs/frontend/performance-evidence.md:
// about 10-25% for bytes, more for blocking time and DOM size, which vary between runs.
// Raise a budget only with new evidence.
const BUDGETS = {
  small: { scriptBytes: 260_000, documentBytes: 20_000, totalBlockingTimeMs: 200, domNodes: 1_200 },
  large: { scriptBytes: 260_000, documentBytes: 64_000, totalBlockingTimeMs: 700, domNodes: 1_200 },
} as const;

// Expected polls in the window: 15 s route refresh and two 15 s status polls everywhere,
// 5 s position state, and the 3 s active-run refresh. Two spare requests absorb
// timer jitter; link prefetch amplification adds seven or more per refresh.
const BACKGROUND_REQUEST_LIMITS: Record<string, number> = {
  "/": 8,
  "/positions": 12,
  "/signals": 8,
  "/runs/active": 16,
};

const results: RouteMeasurement[] = [];

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ page }) => {
  const session = await page.context().newCDPSession(page);
  await session.send("Emulation.setCPUThrottlingRate", { rate: CPU_SLOWDOWN });
  await page.addInitScript(() => {
    const observed = { longTaskBlockingMs: 0, lcp: null as number | null };
    Object.assign(window, { __performanceObserved: observed });
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        observed.longTaskBlockingMs += Math.max(0, entry.duration - 50);
      }
    }).observe({ type: "longtask", buffered: true });
    new PerformanceObserver((list) => {
      const entries = list.getEntries();
      observed.lcp = entries[entries.length - 1].startTime;
    }).observe({ type: "largest-contentful-paint", buffered: true });
  });
});

async function queueActiveRun(page: Page): Promise<string> {
  await page.goto("/run");
  await page.getByRole("button", { name: "Queue historical replay" }).click();
  await page.waitForURL(/\/runs\/[^/]+$/);
  return new URL(page.url()).pathname;
}

async function measureRoute(
  page: Page,
  label: string,
  path: string,
  ready: (page: Page) => Promise<void>,
): Promise<RouteMeasurement> {
  const chartScriptUrls = new Set<string>();
  page.on("response", async (response) => {
    if (response.request().resourceType() !== "script") return;
    const body = await response.text().catch(() => "");
    if (body.includes("recharts-surface")) chartScriptUrls.add(response.url());
  });

  const started = Date.now();
  await page.goto(path);
  await ready(page);
  const chart = page.locator(".recharts-surface");
  const chartRendered = (await chart.count()) > 0;
  const chartVisibleMs = chartRendered ? Date.now() - started : null;
  await page.waitForLoadState("load");
  await page.waitForTimeout(1_000);

  const timing = await page.evaluate((chartUrls) => {
    const resources = performance.getEntriesByType("resource") as PerformanceResourceTiming[];
    const scripts = resources.filter((entry) => entry.initiatorType === "script");
    const navigation = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming;
    const paint = performance.getEntriesByName("first-contentful-paint")[0];
    const observed = (
      window as unknown as {
        __performanceObserved: { longTaskBlockingMs: number; lcp: number | null };
      }
    ).__performanceObserved;
    return {
      documentBytes: navigation.encodedBodySize,
      scriptBytes: scripts.reduce((total, entry) => total + entry.encodedBodySize, 0),
      scriptRequests: scripts.length,
      chartScriptBytes: scripts
        .filter((entry) => chartUrls.includes(entry.name))
        .reduce((total, entry) => total + entry.encodedBodySize, 0),
      firstContentfulPaintMs: paint ? Math.round(paint.startTime) : null,
      largestContentfulPaintMs: observed.lcp === null ? null : Math.round(observed.lcp),
      totalBlockingTimeMs: Math.round(observed.longTaskBlockingMs),
      domNodes: document.getElementsByTagName("*").length,
    };
  }, Array.from(chartScriptUrls));

  const backgroundRequests: Record<string, number> = {};
  const countRequest = (request: Request) => {
    if (!["fetch", "xhr"].includes(request.resourceType())) return;
    const url = new URL(request.url());
    const headers = request.headers();
    const key =
      "next-router-prefetch" in headers
        ? `${url.pathname} (prefetch)`
        : "rsc" in headers
          ? `${url.pathname} (route refresh)`
          : url.pathname;
    backgroundRequests[key] = (backgroundRequests[key] ?? 0) + 1;
  };
  page.on("request", countRequest);
  await page.waitForTimeout(BACKGROUND_WINDOW_MS);
  page.off("request", countRequest);

  return {
    route: label,
    ...timing,
    chartRendered,
    chartVisibleMs,
    backgroundRequests,
  };
}

const visibleHeading = (name: string) => async (page: Page) => {
  await expect(page.getByRole("heading", { name, exact: true }).first()).toBeVisible();
};

test("overview", async ({ page }) => {
  results.push(
    await measureRoute(page, "/", "/", async (current) => {
      await expect(current.getByText("Closed-trade net P&L")).toBeVisible();
      if (fixture === "large") await expect(current.locator(".recharts-surface")).toBeVisible();
    }),
  );
});

test("overview, all sources", async ({ page }) => {
  results.push(
    await measureRoute(page, "/?source=all", "/?source=all", async (current) => {
      await expect(current.locator(".recharts-surface")).toBeVisible();
    }),
  );
});

test("positions", async ({ page }) => {
  results.push(
    await measureRoute(page, "/positions", "/positions", async (current) => {
      await expect(current.getByText("Loading position state…")).toHaveCount(0);
    }),
  );
});

test("signals", async ({ page }) => {
  results.push(
    await measureRoute(page, "/signals", "/signals", async (current) => {
      await expect(current.getByText(/Showing \d+–\d+ of/)).toBeVisible();
    }),
  );
});

test("active run", async ({ page }) => {
  const runPath = await queueActiveRun(page);
  results.push(
    await measureRoute(page, "/runs/active", runPath, visibleHeading("Exact queued configuration")),
  );
});

test.afterAll(() => {
  mkdirSync("performance-results", { recursive: true });
  writeFileSync(
    `performance-results/${fixture}.json`,
    JSON.stringify({ fixture, cpuSlowdown: CPU_SLOWDOWN, results }, null, 2),
  );
});

test("results stay within regression budgets", () => {
  const budget = BUDGETS[fixture === "large" ? "large" : "small"];
  for (const result of results) {
    expect
      .soft(result.scriptBytes, `${result.route} script bytes`)
      .toBeLessThanOrEqual(budget.scriptBytes);
    expect
      .soft(result.documentBytes, `${result.route} document bytes`)
      .toBeLessThanOrEqual(budget.documentBytes);
    expect
      .soft(result.totalBlockingTimeMs, `${result.route} blocking time`)
      .toBeLessThanOrEqual(budget.totalBlockingTimeMs);
    expect.soft(result.domNodes, `${result.route} DOM nodes`).toBeLessThanOrEqual(budget.domNodes);
    if (!result.chartRendered) {
      expect.soft(result.chartScriptBytes, `${result.route} chart script without a chart`).toBe(0);
    }
    const backgroundTotal = Object.values(result.backgroundRequests).reduce((a, b) => a + b, 0);
    expect
      .soft(backgroundTotal, `${result.route} background requests`)
      .toBeLessThanOrEqual(BACKGROUND_REQUEST_LIMITS[result.route.split("?")[0]]);
  }
});

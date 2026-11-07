import { expect, test } from "@playwright/test";

declare global {
  interface Window {
    setVisibilityState(state: DocumentVisibilityState): void;
  }
}

const initialTime = new Date("2026-10-29T14:00:00.000Z");

test("marks last-known prices stale when a hidden positions tab becomes visible", async ({
  page,
}) => {
  await page.clock.install({ time: initialTime });
  await page.addInitScript(() => {
    let visibilityState: DocumentVisibilityState = "visible";
    Object.defineProperty(document, "visibilityState", { get: () => visibilityState });
    Object.defineProperty(window, "setVisibilityState", {
      value: (next: DocumentVisibilityState) => {
        visibilityState = next;
        document.dispatchEvent(new Event("visibilitychange"));
      },
    });
  });
  let priceRequests = 0;
  let startFailedPoll: (() => void) | undefined;
  let finishFailedPoll: (() => void) | undefined;
  const failedPollStarted = new Promise<void>((resolve) => {
    startFailedPoll = resolve;
  });
  await page.route("**/api/position-state", (route) =>
    route.fulfill({
      json: {
        fetched_at: initialTime.toISOString(),
        stale_seconds: 30,
        accounts: [],
        positions: [
          {
            id: 1,
            signal_id: null,
            ticker: "SPY",
            direction: "LONG",
            entry: 100,
            stop: 95,
            target: 110,
            shares: 10,
            remaining_shares: 10,
            exit_price: null,
            outcome: "OPEN",
            pnl: null,
            entry_bar: null,
            exit_bar: null,
            bars_held: null,
            created_at: initialTime.toISOString(),
            closed_at: null,
            source: "live",
            provenance: "Unknown provenance",
            execution: null,
          },
        ],
        pending_entries: [],
        exit_fills: [],
        closed_trades: [],
      },
    }),
  );
  await page.route("**/api/position-prices", async (route) => {
    priceRequests += 1;
    if (priceRequests > 1) {
      startFailedPoll?.();
      await new Promise<void>((resolve) => {
        finishFailedPoll = resolve;
      });
      await route.fulfill({ status: 503, json: { error: "Price service unavailable" } });
      return;
    }

    await new Promise((resolve) => setTimeout(resolve, 250));
    await route.fulfill({
      json: {
        feed: "iex",
        checked_at: initialTime.toISOString(),
        prices: { SPY: { price: 101.25, timestamp: initialTime.toISOString() } },
      },
    });
  });

  await page.goto("/positions");
  await expect(page.getByText("Live price", { exact: true })).toBeVisible();
  await expect(page.getByText("101.25", { exact: false })).toBeVisible();
  await expect(page.getByText(/STALE PRICE/)).toHaveCount(0);

  await page.evaluate(() => {
    window.setVisibilityState("hidden");
  });
  await expect.poll(() => page.evaluate(() => document.visibilityState)).toBe("hidden");
  await page.clock.fastForward(61_000);
  expect(await page.evaluate(() => Date.now())).toBeGreaterThanOrEqual(
    initialTime.getTime() + 61_000,
  );
  await page.evaluate(() => {
    window.setVisibilityState("visible");
  });
  await expect.poll(() => page.evaluate(() => document.visibilityState)).toBe("visible");
  await page.clock.fastForward(1_000);
  await failedPollStarted;

  await expect(page.locator(".position-card")).toContainText("STALE PRICE");
  await expect(page.getByText("Last known price", { exact: true })).toBeVisible();
  await expect(page.getByText("101.25", { exact: false })).toBeVisible();

  finishFailedPoll?.();

  await expect(
    page.getByText("Price service unavailable. Last received prices may be stale."),
  ).toBeVisible();
  await expect(page.getByText(/STALE PRICE/)).toBeVisible();
  await expect(page.getByText("Last known price", { exact: true })).toBeVisible();
  await expect(page.getByText("101.25", { exact: false })).toBeVisible();
  expect(priceRequests).toBeGreaterThan(1);
});

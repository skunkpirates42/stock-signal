import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import type { Trade } from "@/lib/types";
import OpenPositions from "./OpenPositions";

// Run the real hook and polling resource with React state held here, without a browser.
const harness = vi.hoisted(() => ({
  states: [] as unknown[],
  index: 0,
  effects: [] as (() => void | (() => void))[],
  poll: undefined as undefined | (() => Promise<void>),
}));
vi.mock("react", async (original) => ({
  ...(await original<typeof import("react")>()),
  useState: (initial: unknown) => {
    const index = harness.index++;
    if (!(index in harness.states))
      harness.states[index] = typeof initial === "function" ? initial() : initial;
    return [harness.states[index], (value: unknown) => (harness.states[index] = value)];
  },
  useEffect: (effect: () => void | (() => void)) => {
    harness.effects.push(effect);
  },
}));
vi.mock("@/lib/polling", () => ({
  startVisiblePolling: (poll: () => Promise<void>) => {
    harness.poll = poll;
    return () => {};
  },
}));

const livePosition: Trade = {
  id: 1,
  signal_id: null,
  ticker: "SPY",
  direction: "LONG",
  entry: 100,
  stop: 95,
  target: 110,
  shares: 10,
  exit_price: null,
  outcome: "OPEN",
  pnl: null,
  entry_bar: null,
  exit_bar: null,
  bars_held: null,
  created_at: "2026-10-29T13:00:00Z",
  closed_at: null,
  source: "live",
};
const now = new Date("2026-10-29T14:00:00Z");
const render = (currentTime = now) => {
  harness.index = 0;
  harness.effects = [];
  return renderToStaticMarkup(
    createElement(OpenPositions, { positions: [livePosition], now: currentTime }),
  );
};
const pollWith = async (body: unknown) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(body)));
  await harness.poll!();
};

afterEach(() => {
  harness.states = [];
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("renders the unavailable state, not the figures, when position prices are malformed", async () => {
  vi.stubGlobal("document", {});
  render();
  harness.effects.forEach((effect) => effect());
  await pollWith({
    feed: "iex",
    checked_at: "2026-10-29T14:00:00Z",
    prices: { SPY: { price: "987.65", timestamp: "2026-10-29T13:59:59Z" } },
  });
  const html = render();
  expect(html).toContain("Price service unavailable. Last received prices may be stale.");
  expect(html).toContain("Price unavailable");
  expect(html).not.toContain("987.65");
});

it("keeps the last good price, marked stale, when a later response is malformed", async () => {
  vi.stubGlobal("document", {});
  render();
  harness.effects.forEach((effect) => effect());
  await pollWith({
    feed: "iex",
    checked_at: "2026-10-29T14:00:00Z",
    prices: { SPY: { price: 101.25, timestamp: new Date().toISOString() } },
  });
  expect(render()).not.toContain("Price service unavailable");
  expect(render()).toContain("101.25");

  await pollWith({ feed: "iex", checked_at: "2026-10-29T14:00:05Z", prices: null });
  const html = render();
  expect(html).toContain("Price service unavailable");
  expect(html).toContain("Last known price");
  expect(html).toContain("101.25");
});

it("ages the last received mark against the visible clock after polling completes", async () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-29T14:00:00Z"));
  vi.stubGlobal("document", {});
  render();
  harness.effects.forEach((effect) => effect());
  await pollWith({
    feed: "iex",
    checked_at: "2026-10-29T14:00:00Z",
    prices: { SPY: { price: 101.25, timestamp: "2026-10-29T14:00:00Z" } },
  });
  expect(render()).not.toContain("STALE PRICE");

  const visibleTimeAfterThreshold = new Date("2026-10-29T14:01:01Z");
  expect(render(visibleTimeAfterThreshold)).toContain("STALE PRICE");
  expect(render(visibleTimeAfterThreshold)).toContain("101.25");
});

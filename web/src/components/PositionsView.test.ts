import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import type { PositionState } from "@/lib/execution";
import PositionsView from "./PositionsView";

// Drive the component's polling callback between clock ticks without a browser.
const harness = vi.hoisted(() => ({
  states: [] as unknown[],
  index: 0,
  effect: undefined as undefined | (() => () => void),
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
  useEffect: (effect: () => () => void) => {
    harness.effect = effect;
  },
}));
vi.mock("@/lib/polling", () => ({
  startVisiblePolling: (poll: () => Promise<void>) => {
    harness.poll = poll;
    return () => {};
  },
}));
vi.mock("./OpenPositions", () => ({ default: () => null }));
vi.mock("./FillsTable", () => ({ default: () => null }));

const render = () => {
  harness.index = 0;
  return renderToStaticMarkup(createElement(PositionsView));
};
let cleanup: (() => void) | undefined;
afterEach(() => {
  cleanup?.();
  cleanup = undefined;
  harness.states = [];
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("keeps newly fetched position data fresh between one-second clock ticks", async () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-29T14:00:00.000Z"));
  vi.stubGlobal("document", {});
  render();
  cleanup = harness.effect!();
  for (let second = 0; second <= 10; second += 5) {
    vi.setSystemTime(new Date(`2026-10-29T14:00:${String(second).padStart(2, "0")}.500Z`));
    const data: PositionState = {
      fetched_at: new Date().toISOString(),
      stale_seconds: 30,
      accounts: [],
      positions: [],
      pending_entries: [],
      exit_fills: [],
      closed_trades: [],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => data }));
    await harness.poll!();
    expect(render()).not.toContain("Position data is stale");
    await vi.advanceTimersByTimeAsync(1000);
    expect(render()).not.toContain("Position data is stale");
  }
  await vi.advanceTimersByTimeAsync(31000);
  expect(render()).toContain("Position data is stale");
  expect(render()).toContain('<details class="disclosure">');
  expect(render()).not.toMatch(/<details[^>]*\bopen/);
  expect(render()).toMatch(/<summary>.*Position data is stale.*<\/summary>/);

  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  await harness.poll!();
  expect(render()).toMatch(/<summary>.*Position service unavailable.*<\/summary>/);
  expect(render()).toContain("current holdings and protection are unconfirmed");
});

import { afterEach, expect, it, vi } from "vitest";
import { startPolledResource, type PolledResource } from "./polledResource";
import { readPositionPrices, type PositionPrices } from "./prices";

const visibleDoc = {
  visibilityState: "visible" as DocumentVisibilityState,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
};
const goodPrices: PositionPrices = {
  feed: "iex",
  checked_at: "2026-10-29T14:00:00Z",
  prices: { SPY: { price: 101.5, timestamp: "2026-10-29T13:59:58Z" } },
};
const serve = (...bodies: unknown[]) => {
  const fetchMock = vi.fn();
  for (const body of bodies) fetchMock.mockResolvedValueOnce(Response.json(body));
  vi.stubGlobal("fetch", fetchMock);
};

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function pollPrices() {
  const states: PolledResource<PositionPrices>[] = [];
  const stop = startPolledResource(
    "/api/position-prices",
    readPositionPrices,
    (next) => states.push(next),
    visibleDoc,
    100,
  );
  return { states, stop };
}

it("publishes parsed data, then keeps it but marks failure when a later body is malformed", async () => {
  vi.useFakeTimers();
  serve(goodPrices, { feed: "iex", checked_at: "x", prices: { SPY: { price: "101.5" } } });
  const { states, stop } = pollPrices();
  await vi.advanceTimersByTimeAsync(100);
  stop();
  expect(states.map(({ data, failed }) => ({ data, failed }))).toEqual([
    { data: goodPrices, failed: false },
    { data: goodPrices, failed: true },
  ]);
  expect(states.every((state) => state.checkedAt instanceof Date)).toBe(true);
});

it("never publishes malformed data, even on the first poll", async () => {
  serve({ error: "Market data unavailable" });
  const { states, stop } = pollPrices();
  await vi.waitFor(() => expect(states).toHaveLength(1));
  stop();
  expect(states[0]).toMatchObject({ data: null, failed: true });
});

it("treats a non-ok response as a failure", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 503 })));
  const { states, stop } = pollPrices();
  await vi.waitFor(() => expect(states).toHaveLength(1));
  stop();
  expect(states[0]).toMatchObject({ data: null, failed: true });
});

it("stops publishing and aborts the request once stopped", async () => {
  let requestSignal: AbortSignal | undefined;
  vi.stubGlobal(
    "fetch",
    vi.fn((_url: string, init: RequestInit) => {
      requestSignal = init.signal ?? undefined;
      return new Promise(() => {});
    }),
  );
  const { states, stop } = pollPrices();
  stop();
  expect(requestSignal?.aborted).toBe(true);
  expect(states).toEqual([]);
});

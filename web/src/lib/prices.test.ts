import { describe, expect, it } from "vitest";
import { markedPosition, priceIsStale, readPositionPrices } from "./prices";
import type { Trade } from "./types";

export const position: Trade = {
  id: 1,
  signal_id: null,
  ticker: "SPY",
  direction: "LONG",
  entry: 100,
  stop: 95,
  target: 110,
  shares: 10,
  remaining_shares: 4,
  exit_price: null,
  outcome: "OPEN",
  pnl: null,
  entry_bar: null,
  exit_bar: null,
  bars_held: null,
  created_at: "2026-10-28T15:00:00Z",
  closed_at: null,
  source: "live",
};

describe("display marks", () => {
  it("marks remaining shares and preserves breached levels", () => {
    expect(markedPosition(position, 112)).toEqual({ pnl: 48, toStop: 17, toTarget: -2 });
    expect(markedPosition({ ...position, direction: "SHORT", stop: 105, target: 90 }, 88)).toEqual({
      pnl: 48,
      toStop: 17,
      toTarget: -2,
    });
    expect(markedPosition({ ...position, remaining_shares: 0 }, 112).pnl).toBe(0);
    expect(markedPosition(position, 94).pnl).toBe(-24);
  });
  it("uses trade age rather than fetch age", () => {
    const mark = { price: 100, timestamp: "2026-10-28T15:00:00Z" };
    expect(priceIsStale(mark, new Date("2026-10-28T15:01:00Z"))).toBe(false);
    expect(priceIsStale(mark, new Date("2026-10-28T15:01:01Z"))).toBe(true);
    expect(priceIsStale({ ...mark, timestamp: "invalid" }, new Date())).toBe(true);
  });
});

describe("readPositionPrices", () => {
  const response = {
    feed: "iex",
    checked_at: "2026-10-29T14:00:00Z",
    prices: { SPY: { price: 101.5, timestamp: "2026-10-29T13:59:58Z" } },
  };

  it("returns the typed prices for a well-formed response", () => {
    expect(readPositionPrices(response, "position-prices")).toEqual(response);
  });

  it("rejects a mark whose price is missing, non-numeric or not positive", () => {
    for (const price of [undefined, "101.5", 0, -1]) {
      expect(() =>
        readPositionPrices(
          { ...response, prices: { SPY: { ...response.prices.SPY, price } } },
          "position-prices",
        ),
      ).toThrow(/^position-prices\.prices\.SPY\.price: expected/);
    }
  });

  it("rejects an error body in place of prices", () => {
    expect(() =>
      readPositionPrices({ error: "Market data unavailable" }, "position-prices"),
    ).toThrow("position-prices.feed: expected iex");
  });
});

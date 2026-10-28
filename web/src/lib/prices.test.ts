import { describe, expect, it } from "vitest";
import { markedPosition, priceIsStale } from "./prices";
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

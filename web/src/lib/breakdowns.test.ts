import { describe, expect, it } from "vitest";
import { breakdownRows } from "@/lib/breakdowns";
import type { Breakdown } from "@/lib/types";

const row = (n: number, wins: number, pnl: number): Breakdown => ({
  n,
  wins,
  win_rate: n === 0 ? 0 : wins / n,
  pnl,
});

describe("breakdownRows", () => {
  it("sorts by P&L, most profitable first", () => {
    const rows = breakdownRows({ AAPL: row(10, 4, -20), NVDA: row(10, 6, 40) });
    expect(rows.map((r) => r.name)).toEqual(["NVDA", "AAPL"]);
  });

  it("sizes each bar against the largest magnitude, not the largest gain", () => {
    const rows = breakdownRows({ NVDA: row(10, 6, 40), AAPL: row(10, 2, -80) });
    expect(rows.find((r) => r.name === "AAPL")?.share).toBe(1);
    expect(rows.find((r) => r.name === "NVDA")?.share).toBe(0.5);
  });

  it("carries the original breakdown fields through", () => {
    const [only] = breakdownRows({ SPY: row(8, 2, 5) });
    expect(only).toMatchObject({ name: "SPY", n: 8, wins: 2, pnl: 5 });
  });

  it("returns an empty array for no rows", () => {
    expect(breakdownRows({})).toEqual([]);
  });
});

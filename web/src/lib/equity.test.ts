import { describe, expect, it } from "vitest";
import { summarizeEquityCurve } from "@/lib/equity";

const point = (label: string, equity: number) => ({ label, equity, pnl: 0 });

describe("summarizeEquityCurve", () => {
  it("states the start, end, low and high in words a screen reader can read", () => {
    const summary = summarizeEquityCurve([
      point("start", 100000),
      point("2026-10-01T14:30:00", 98500.5),
      point("2026-10-02T15:00:00", 101250),
      point("2026-10-03T16:00:00", 100400),
    ]);
    expect(summary).toBe(
      "Equity went from $100,000.00 at start to $100,400.00 at 2026-10-03 16:00 UTC, " +
        "with a low of $98,500.50 and a high of $101,250.00 across 4 points.",
    );
  });
});

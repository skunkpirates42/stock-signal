import { describe, expect, it } from "vitest";
import { parseIndicators, voteTally } from "@/lib/indicators";

const REAL = JSON.stringify({
  votes: { rsi: "neutral", price_vs_sma20: "bear", sma20_vs_sma50: "bear",
           price_vs_vwap: "bull", macd: "bear", bb: "neutral" },
  values: { close: 395.61, rsi: 49.05, sma20: 395.87, sma50: 396.13, vwap: 392.95,
            macd: -0.205, bb_pct: 0.393, volume_ratio: 2.637, atr: 0.745 },
  tally: { bull: 1, bear: 3, neutral: 2 },
});

describe("parseIndicators", () => {
  it("returns all six indicators in display order", () => {
    const rows = parseIndicators(REAL);
    expect(rows.map((r) => r.indicator)).toEqual([
      "rsi", "price_vs_sma20", "sma20_vs_sma50", "price_vs_vwap", "macd", "bb",
    ]);
  });

  it("carries each vote through", () => {
    const rows = parseIndicators(REAL);
    expect(rows.find((r) => r.indicator === "macd")?.vote).toBe("bear");
    expect(rows.find((r) => r.indicator === "price_vs_vwap")?.vote).toBe("bull");
  });

  it("gives every row a human label", () => {
    expect(parseIndicators(REAL).find((r) => r.indicator === "bb")?.label)
      .toBe("BB %B");
  });

  it("shows the value that produced the vote", () => {
    const rows = parseIndicators(REAL);
    expect(rows.find((r) => r.indicator === "rsi")?.detail).toContain("49.05");
    expect(rows.find((r) => r.indicator === "price_vs_sma20")?.detail).toContain("395.61");
  });

  it("returns empty for null rather than throwing", () => {
    expect(parseIndicators(null)).toEqual([]);
  });

  it("returns empty for malformed JSON rather than throwing", () => {
    expect(parseIndicators("{not json")).toEqual([]);
  });

  it("returns empty when the votes key is missing", () => {
    expect(parseIndicators(JSON.stringify({ values: {} }))).toEqual([]);
  });
});

describe("voteTally", () => {
  it("counts each side", () => {
    expect(voteTally(parseIndicators(REAL))).toEqual({ bull: 1, bear: 3, neutral: 2 });
  });

  it("handles an empty list", () => {
    expect(voteTally([])).toEqual({ bull: 0, bear: 0, neutral: 0 });
  });
});

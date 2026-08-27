import { describe, expect, it } from "vitest";
import { atrArithmetic, parseAtr, parseIndicators, voteTally } from "@/lib/indicators";

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

  it("returns empty when votes is not an object", () => {
    expect(parseIndicators(JSON.stringify({ votes: "oops" }))).toEqual([]);
  });

  it("handles null values without throwing", () => {
    const withNull = JSON.stringify({
      votes: { rsi: "bull" },
      values: { rsi: null },
    });
    const rows = parseIndicators(withNull);
    expect(rows).toHaveLength(1);
    expect(rows[0]?.indicator).toBe("rsi");
    expect(rows[0]?.vote).toBe("bull");
    expect(rows[0]?.detail).toContain("—");
  });

  it("handles non-numeric values without throwing", () => {
    const withString = JSON.stringify({
      votes: { rsi: "bull" },
      values: { rsi: "invalid" },
    });
    const rows = parseIndicators(withString);
    expect(rows).toHaveLength(1);
    expect(rows[0]?.indicator).toBe("rsi");
    expect(rows[0]?.vote).toBe("bull");
    expect(rows[0]?.detail).toContain("—");
  });

  it("returns only present indicators in ORDER", () => {
    const partial = JSON.stringify({
      votes: { rsi: "bull", macd: "bear", bb: "neutral" },
      values: { rsi: 30, macd: -0.1, bb_pct: 0.5 },
    });
    const rows = parseIndicators(partial);
    expect(rows.map((r) => r.indicator)).toEqual(["rsi", "macd", "bb"]);
    expect(rows).toHaveLength(3);
  });

  it("handles top-level null without throwing", () => {
    expect(parseIndicators("null")).toEqual([]);
  });

  it("handles top-level array without throwing", () => {
    expect(parseIndicators("[1,2]")).toEqual([]);
  });

  it("handles top-level number without throwing", () => {
    expect(parseIndicators("42")).toEqual([]);
  });
});

describe("parseAtr", () => {
  it("reads the atr value out of the raw values blob", () => {
    expect(parseAtr(REAL)).toBeCloseTo(0.745, 3);
  });

  it("returns null for null", () => {
    expect(parseAtr(null)).toBeNull();
  });

  it("returns null for malformed JSON", () => {
    expect(parseAtr("{not json")).toBeNull();
  });

  it("returns null when atr is missing", () => {
    expect(parseAtr(JSON.stringify({ votes: {}, values: {} }))).toBeNull();
  });

  it("returns null when atr is non-numeric", () => {
    expect(parseAtr(JSON.stringify({ votes: {}, values: { atr: "oops" } }))).toBeNull();
  });
});

describe("atrArithmetic", () => {
  it("subtracts for the stop and adds for the target on a LONG", () => {
    const result = atrArithmetic("LONG", 0.75);
    expect(result.stopOperator).toBe("-");
    expect(result.targetOperator).toBe("+");
    expect(result.stopMultiplier).toBe(1.5);
    expect(result.targetMultiplier).toBe(3.0);
    expect(result.atr).toBe(0.75);
  });

  it("inverts the signs on a SHORT", () => {
    const result = atrArithmetic("SHORT", 0.75);
    expect(result.stopOperator).toBe("+");
    expect(result.targetOperator).toBe("-");
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

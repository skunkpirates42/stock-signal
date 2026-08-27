import { describe, expect, it } from "vitest";
import { filterSignals } from "@/lib/filters";
import type { Signal } from "@/lib/types";

function signal(over: Partial<Signal>): Signal {
  return {
    id: 1, ticker: "AAPL", direction: "LONG", confidence: 0.7,
    entry: 100, stop: 98, target: 104, rr: 2,
    bar_timestamp: "2026-07-15 19:55:00+00:00",
    created_at: "2026-07-15T20:00:00+00:00",
    regime: "BULL", source: "live",
    synthesis_source: "groq:qwen/qwen3.6-27b",
    reasoning: "x", indicators_json: "{}",
    ...over,
  };
}

describe("filterSignals", () => {
  const all = [
    signal({ id: 1, ticker: "AAPL", direction: "LONG", confidence: 0.7 }),
    signal({ id: 2, ticker: "NVDA", direction: "SHORT", confidence: 0.9 }),
    signal({ id: 3, ticker: "AAPL", direction: "WAIT", confidence: 0.55 }),
  ];

  it("returns everything with empty criteria", () => {
    expect(filterSignals(all, {})).toHaveLength(3);
  });

  it("filters by ticker", () => {
    expect(filterSignals(all, { ticker: "AAPL" }).map((s) => s.id)).toEqual([1, 3]);
  });

  it("filters by direction", () => {
    expect(filterSignals(all, { direction: "SHORT" }).map((s) => s.id)).toEqual([2]);
  });

  it("filters by minimum confidence inclusively", () => {
    expect(filterSignals(all, { minConfidence: 0.7 }).map((s) => s.id)).toEqual([1, 2]);
  });

  it("filters by date range on bar_timestamp", () => {
    const older = signal({ id: 4, bar_timestamp: "2026-06-01 10:00:00+00:00" });
    const result = filterSignals([...all, older], { from: "2026-07-01" });
    expect(result.map((s) => s.id)).toEqual([1, 2, 3]);
  });

  it("combines criteria", () => {
    expect(filterSignals(all, { ticker: "AAPL", direction: "LONG" }).map((s) => s.id))
      .toEqual([1]);
  });

  it("returns empty when nothing matches", () => {
    expect(filterSignals(all, { ticker: "TSLA" })).toEqual([]);
  });
});

import { describe, expect, it } from "vitest";
import type { Metric } from "@/lib/demo";
import { describeObservation } from "@/lib/observation";

const saved = (value: number, unit = "USD"): Metric => ({
  observation: { availability: "available", value, reason: null, detail: null },
  unit,
  basis: "Saved basis",
  source_pointer: null,
});
const missing = (detail: string): Metric => ({
  observation: { availability: "unavailable", value: null, reason: "not_recorded", detail },
  unit: "USD",
  basis: "Saved basis",
  source_pointer: null,
});

describe("describeObservation", () => {
  it("signs and tones a saved P&L amount", () => {
    expect(describeObservation("realized_net_pnl", saved(2220.33))).toEqual({
      text: "+$2,220.33",
      tone: "positive",
      reason: null,
    });
  });

  it("tones a negative P&L amount", () => {
    expect(describeObservation("marked_net_pnl", saved(-12.5))).toEqual({
      text: "-$12.50",
      tone: "negative",
      reason: null,
    });
  });

  it("keeps a saved zero as zero, not unavailable", () => {
    expect(describeObservation("realized_net_pnl", saved(0))).toMatchObject({
      text: "$0.00",
      tone: "muted",
    });
  });

  it("leaves costs, drawdown and exposure unsigned and untoned", () => {
    expect(describeObservation("realized_max_drawdown", saved(3856.8))).toEqual({
      text: "$3,856.80",
      tone: "muted",
      reason: null,
    });
  });

  it("states the per-session unit", () => {
    expect(describeObservation("marked_net_per_session", saved(26.5, "USD/session")).text).toBe(
      "+$26.50/session",
    );
  });

  it("keeps counts as plain numbers", () => {
    expect(describeObservation("closed_trades", saved(2734, "count"))).toEqual({
      text: "2734",
      tone: "muted",
      reason: null,
    });
  });

  it("names other units", () => {
    expect(describeObservation("hit_rate", saved(0.52, "ratio")).text).toBe("0.52 ratio");
  });

  it("never shows an unavailable value as a number and keeps its reason", () => {
    expect(describeObservation("fees", missing("Fees were not saved."))).toEqual({
      text: "Unavailable",
      tone: "muted",
      reason: "Fees were not saved.",
    });
  });

  it("marks a metric absent from the result unavailable", () => {
    expect(describeObservation("fees", undefined)).toEqual({
      text: "Unavailable",
      tone: "muted",
      reason: "No saved metric.",
    });
  });
});

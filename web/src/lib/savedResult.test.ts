import { describe, expect, it } from "vitest";
import type { Artifact, Metric } from "@/lib/demo";
import { groupArtifactsByKind, headlineFigures, metricValue, savedMetricGroups, untrackedCostComponents } from "@/lib/savedResult";

const REALIZED = "Realized closed trades; net of recorded costs";
const MARKED = "Marked portfolio; latest observed close";

const saved = (value: number, basis: string, unit = "USD"): Metric => ({
  observation: { availability: "available", value, reason: null, detail: null }, unit, basis, source_pointer: "/comparison",
});
const missing = (detail: string, basis = "No separate saved accounting amount."): Metric => ({
  observation: { availability: "unavailable", value: null, reason: "not_recorded", detail }, unit: "USD", basis, source_pointer: null,
});

const metrics: Record<string, Metric> = {
  realized_net_pnl: saved(2220.33, REALIZED),
  gross_pnl: saved(12928.35, REALIZED),
  recorded_costs: saved(10707.82, REALIZED),
  realized_max_drawdown: saved(3856.8, REALIZED),
  closed_trades: saved(2734, REALIZED, "count"),
  censored_positions: saved(4, "Positions open at window end", "count"),
  marked_net_pnl: saved(-12.5, MARKED),
  marked_max_drawdown: saved(3881.57, MARKED),
  marked_net_per_session: saved(26.5, MARKED, "USD/session"),
  max_gross_exposure: saved(81443.32, MARKED),
  spread_cost: missing("Spread total was not saved."),
  slippage_cost: missing("Slippage total was not saved."),
  fees: missing("Fees were not saved."),
  borrow_cost: missing("Borrow is not modeled."),
};

const artifact = (kind: string): Artifact => ({
  record_type: "artifact", id: `${kind}-id`, result_id: "result", kind, sha256: "a".repeat(64), mime_type: "application/json", byte_size: 1,
});

describe("metricValue", () => {
  it("formats saved amounts", () => expect(metricValue("realized_net_pnl", metrics.realized_net_pnl)).toBe("+$2,220.33"));
  it("keeps counts as plain numbers", () => expect(metricValue("closed_trades", metrics.closed_trades)).toBe("2734"));
  it("says why a value is unavailable", () => expect(metricValue("fees", metrics.fees)).toBe("Unavailable: Fees were not saved."));
  it("marks a missing metric unavailable", () => expect(metricValue("fees", undefined)).toBe("Unavailable"));
});

describe("headlineFigures", () => {
  it("leads with the realized figures and labels the marked ones", () => {
    const figures = headlineFigures(metrics);
    expect(figures.map((figure) => figure.label)).toEqual(["Realized net P&L", "Closed trades", "Realized max drawdown", "Marked net P&L", "Marked max drawdown"]);
    expect(figures.slice(3).every((figure) => figure.note === "Marked to latest close")).toBe(true);
  });

  it("colors P&L by sign and leaves amounts muted", () => {
    const [realized, , drawdown, marked] = headlineFigures(metrics);
    expect(realized.tone).toBe("positive");
    expect(marked.tone).toBe("negative");
    expect(drawdown).toMatchObject({ value: "$3,856.80", tone: "muted" });
  });

  it("never shows a missing headline as zero", () => {
    const [realized] = headlineFigures({});
    expect(realized).toMatchObject({ value: "Unavailable", tone: "muted" });
  });
});

describe("savedMetricGroups", () => {
  it("states each group's basis once and only repeats a basis that differs", () => {
    const [realized, marked] = savedMetricGroups(metrics);
    expect(realized.basis).toBe(REALIZED);
    expect(realized.rows.filter((row) => row.ownBasis !== null)).toEqual([
      expect.objectContaining({ name: "censored_positions", ownBasis: "Positions open at window end" }),
    ]);
    expect(marked.basis).toBe(MARKED);
    expect(marked.rows.every((row) => row.ownBasis === null)).toBe(true);
  });

  it("keeps a metric absent from the result as an unavailable row", () => {
    const withoutCensored = { ...metrics };
    delete withoutCensored.censored_positions;
    const [realized] = savedMetricGroups(withoutCensored);
    expect(realized.rows.find((row) => row.name === "censored_positions")).toMatchObject({ value: "Unavailable", ownBasis: null });
  });

  it("adds a cost group only for components that were saved", () => {
    expect(savedMetricGroups(metrics)).toHaveLength(2);
    const groups = savedMetricGroups({ ...metrics, fees: saved(3, "Saved fee total") });
    expect(groups[2]).toMatchObject({ title: "Cost components", basis: "Saved fee total", rows: [expect.objectContaining({ name: "fees", value: "$3.00" })] });
  });
});

describe("untrackedCostComponents", () => {
  it("lists every unavailable or missing component with its reason", () => {
    expect(untrackedCostComponents(metrics)).toEqual([
      { label: "spread", reason: "Spread total was not saved. No separate saved accounting amount." },
      { label: "slippage", reason: "Slippage total was not saved. No separate saved accounting amount." },
      { label: "fees", reason: "Fees were not saved. No separate saved accounting amount." },
      { label: "borrow", reason: "Borrow is not modeled. No separate saved accounting amount." },
      { label: "dividends", reason: "No saved metric." },
    ]);
  });

  it("drops a component that was saved", () => {
    expect(untrackedCostComponents({ ...metrics, fees: saved(3, "Saved fee total") }).map((item) => item.label)).not.toContain("fees");
  });
});

describe("groupArtifactsByKind", () => {
  it("files known kinds and puts everything else under reproducibility", () => {
    const groups = groupArtifactsByKind(["cashflows", "diagnostics", "dataset_metadata", "manifest", "trades"].map(artifact));
    expect(groups.accounting.map((item) => item.kind)).toEqual(["cashflows"]);
    expect(groups.quality.map((item) => item.kind)).toEqual(["diagnostics"]);
    expect(groups.data.map((item) => item.kind)).toEqual(["dataset_metadata"]);
    expect(groups.reproducibility.map((item) => item.kind)).toEqual(["manifest", "trades"]);
  });
});

import { describe, expect, it } from "vitest";
import { buildComparisonTable, formatWindowDates } from "./research-comparison";
import type { Result } from "./demo";

const DEVELOPMENT = { name: "development", role: "development" as const, start: "2026-03-01T00:00:00Z", end_exclusive: "2026-07-01T00:00:00Z" };
const HOLDOUT = { name: "holdout", role: "holdout" as const, start: "2026-07-01T00:00:00Z", end_exclusive: "2026-09-01T00:00:00Z" };

function result(id: string, variant: string, window: Result["window"], pnl: number | null, overrides: { synthetic?: boolean; retrospective?: boolean; coverage?: Result["accounting"]["coverage"] } = {}): Result {
  const observation = pnl === null
    ? { availability: "unavailable" as const, value: null, reason: "not_recorded" as const, detail: "Not saved" }
    : { availability: "available" as const, value: pnl, reason: null, detail: null };
  return {
    id, variant, window,
    provenance: { synthetic: overrides.synthetic ?? false, retrospective: overrides.retrospective ?? true },
    accounting: { coverage: overrides.coverage ?? "incomplete" },
    metrics: { realized_net_pnl: { observation, unit: "USD", basis: "Realized", source_pointer: "/comparison" } },
  } as unknown as Result;
}

describe("buildComparisonTable", () => {
  it("lays out variants as rows in strategy order and windows as columns by start date", () => {
    const table = buildComparisonTable([
      result("both-hold", "both", HOLDOUT, 1),
      result("rvol-dev", "rvol", DEVELOPMENT, 2),
      result("base-hold", "baseline", HOLDOUT, 3),
      result("strength-dev", "strength", DEVELOPMENT, 4),
      result("base-dev", "baseline", DEVELOPMENT, 5),
    ]);
    expect(table.columns.map((column) => column.name)).toEqual(["development", "holdout"]);
    expect(table.rows.map((row) => row.variant)).toEqual(["baseline", "strength", "rvol", "both"]);
    expect(table.rows[0].cells.map((cell) => cell.map((entry) => entry.id))).toEqual([["base-dev"], ["base-hold"]]);
  });

  it("leaves a missing cell empty when a variant appears in only one window", () => {
    const table = buildComparisonTable([result("base-dev", "baseline", DEVELOPMENT, 5), result("rvol-hold", "rvol", HOLDOUT, -2)]);
    expect(table.rows.find((row) => row.variant === "rvol")?.cells.map((cell) => cell.length)).toEqual([0, 1]);
    expect(table.rows.find((row) => row.variant === "baseline")?.cells.map((cell) => cell.length)).toEqual([1, 0]);
  });

  it("places unknown variants after the known ones, alphabetically", () => {
    const table = buildComparisonTable([result("z", "zeta", DEVELOPMENT, 1), result("a", "alpha", DEVELOPMENT, 1), result("b", "both", DEVELOPMENT, 1)]);
    expect(table.rows.map((row) => row.variant)).toEqual(["both", "alpha", "zeta"]);
  });

  it("keeps every result when two share a variant and window", () => {
    const table = buildComparisonTable([result("one", "baseline", DEVELOPMENT, 1), result("two", "baseline", DEVELOPMENT, 2, { synthetic: true })]);
    expect(table.rows[0].cells[0].map((entry) => entry.id)).toEqual(["one", "two"]);
  });

  it("separates windows that share a name but not dates", () => {
    const table = buildComparisonTable([result("a", "baseline", DEVELOPMENT, 1), result("b", "baseline", { ...DEVELOPMENT, start: "2026-02-01T00:00:00Z" }, 1)]);
    expect(table.columns.map((column) => column.dates)).toEqual(["Feb 1 – Jul 1, 2026", "Mar 1 – Jul 1, 2026"]);
  });

  it("flags synthetic results per cell", () => {
    const table = buildComparisonTable([result("real", "baseline", DEVELOPMENT, 1), result("fake", "baseline", HOLDOUT, 1, { synthetic: true })]);
    expect(table.rows[0].cells.map((cell) => cell[0].synthetic)).toEqual([false, true]);
  });

  it("shows unavailable P&L as Unavailable, never a number", () => {
    const table = buildComparisonTable([result("missing", "baseline", DEVELOPMENT, null), result("zero", "baseline", HOLDOUT, 0)]);
    expect(table.rows[0].cells[0][0]).toMatchObject({ pnlLabel: "Unavailable", tone: "muted" });
    expect(table.rows[0].cells[1][0]).toMatchObject({ pnlLabel: "$0.00", tone: "muted" });
  });

  it("formats available P&L with its sign and tone", () => {
    const table = buildComparisonTable([result("gain", "baseline", DEVELOPMENT, 2220.33), result("loss", "baseline", HOLDOUT, -73.13)]);
    expect(table.rows[0].cells.map((cell) => [cell[0].pnlLabel, cell[0].tone])).toEqual([["+$2,220.33", "positive"], ["-$73.13", "negative"]]);
  });

  it("states shared coverage once and leaves cells unlabelled", () => {
    const table = buildComparisonTable([result("a", "baseline", DEVELOPMENT, 1), result("b", "rvol", HOLDOUT, 1)]);
    expect(table.sharedCoverage).toBe("incomplete");
    expect(table.rows.flatMap((row) => row.cells.flat()).map((entry) => entry.coverage)).toEqual([null, null]);
  });

  it("labels coverage per cell when results disagree", () => {
    const table = buildComparisonTable([result("a", "baseline", DEVELOPMENT, 1), result("b", "baseline", HOLDOUT, 1, { coverage: "complete" })]);
    expect(table.sharedCoverage).toBeNull();
    expect(table.rows[0].cells.map((cell) => cell[0].coverage)).toEqual(["incomplete", "complete"]);
  });

  it("labels retrospective evaluation per cell only when results disagree", () => {
    expect(buildComparisonTable([result("a", "baseline", DEVELOPMENT, 1)]).sharedRetrospective).toBe(true);
    const mixed = buildComparisonTable([result("a", "baseline", DEVELOPMENT, 1), result("b", "baseline", HOLDOUT, 1, { retrospective: false })]);
    expect(mixed.sharedRetrospective).toBeNull();
    expect(mixed.rows[0].cells.map((cell) => cell[0].retrospective)).toEqual([true, false]);
  });

  it("keeps the exact inclusive and exclusive bounds for each window", () => {
    const table = buildComparisonTable([result("a", "baseline", DEVELOPMENT, 1)]);
    expect(table.columns[0].exactRange).toBe("2026-03-01 00:00 UTC inclusive to 2026-07-01 00:00 UTC exclusive");
  });

  it("returns an empty table with no shared values for an empty page", () => {
    expect(buildComparisonTable([])).toEqual({ columns: [], rows: [], sharedCoverage: null, sharedRetrospective: null });
  });
});

describe("formatWindowDates", () => {
  it("shows the year once when both dates share it", () => {
    expect(formatWindowDates("2026-03-01T00:00:00Z", "2026-07-01T00:00:00Z")).toBe("Mar 1 – Jul 1, 2026");
  });

  it("shows both years when the window crosses a year", () => {
    expect(formatWindowDates("2025-12-01T00:00:00Z", "2026-02-01T00:00:00Z")).toBe("Dec 1, 2025 – Feb 1, 2026");
  });

  it("reads dates in UTC, not local time", () => {
    expect(formatWindowDates("2026-03-01T00:00:00Z", "2026-03-31T23:30:00Z")).toBe("Mar 1 – Mar 31, 2026");
  });

  it("falls back to the raw timestamps when a date does not parse", () => {
    expect(formatWindowDates("start", "2026-07-01T00:00:00Z")).toBe("start – 2026-07-01 00:00 UTC");
  });
});

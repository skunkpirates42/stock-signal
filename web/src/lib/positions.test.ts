import { describe, expect, it } from "vitest";
import { formatCurrency } from "@/lib/format";
import { distanceToStop, distanceToTarget, isStale } from "@/lib/positions";

describe("distanceToStop", () => {
  it("is positive below entry for a LONG", () => {
    const result = distanceToStop({ direction: "LONG", entry: 100, stop: 97 });
    expect(result.dollars).toBe(3);
    expect(result.percent).toBeCloseTo(0.03);
  });

  it("is positive above entry for a SHORT", () => {
    const result = distanceToStop({ direction: "SHORT", entry: 100, stop: 103 });
    expect(result.dollars).toBe(3);
    expect(result.percent).toBeCloseTo(0.03);
  });

  it("goes negative when the stop is on the wrong side of entry", () => {
    const result = distanceToStop({ direction: "LONG", entry: 100, stop: 102 });
    expect(result.dollars).toBe(-2);
  });

  it("keeps its sign when rendered as the signed dollar delta it is", () => {
    // PositionCard renders this column with formatCurrency, not formatPrice — the
    // malformed-data signal above must survive to render, not get Math.abs'd away.
    const result = distanceToStop({ direction: "LONG", entry: 100, stop: 102 });
    expect(formatCurrency(result.dollars)).toBe("-$2.00");
  });
});

describe("distanceToTarget", () => {
  it("is positive above entry for a LONG", () => {
    const result = distanceToTarget({ direction: "LONG", entry: 100, target: 106 });
    expect(result.dollars).toBe(6);
    expect(result.percent).toBeCloseTo(0.06);
  });

  it("is positive below entry for a SHORT", () => {
    const result = distanceToTarget({ direction: "SHORT", entry: 100, target: 94 });
    expect(result.dollars).toBe(6);
    expect(result.percent).toBeCloseTo(0.06);
  });
});

describe("isStale", () => {
  it("is false for a position opened minutes ago", () => {
    const now = new Date("2026-07-15T20:30:00Z");
    expect(isStale("2026-07-15T20:00:00Z", now)).toBe(false);
  });

  it("is true for a position opened more than a day ago", () => {
    const now = new Date("2026-08-26T12:00:00Z");
    expect(isStale("2026-07-15T20:00:00Z", now)).toBe(true);
  });

  it("is false exactly at the boundary and true just past it", () => {
    const opened = "2026-07-15T20:00:00Z";
    const exactlyOneDayLater = new Date("2026-07-16T20:00:00Z");
    const oneMsPast = new Date("2026-07-16T20:00:00.001Z");
    expect(isStale(opened, exactlyOneDayLater)).toBe(false);
    expect(isStale(opened, oneMsPast)).toBe(true);
  });
});

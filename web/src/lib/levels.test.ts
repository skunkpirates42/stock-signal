import { describe, expect, it } from "vitest";
import { entryFraction } from "@/lib/levels";

describe("entryFraction", () => {
  it("puts a 2:1 long entry one third along the axis", () => {
    expect(entryFraction(95, 100, 110)).toBeCloseTo(1 / 3);
  });

  it("puts a 2:1 short entry one third along the axis", () => {
    expect(entryFraction(105, 100, 90)).toBeCloseTo(1 / 3);
  });

  it("returns null when stop and target are the same price", () => {
    expect(entryFraction(100, 100, 100)).toBeNull();
  });

  it("reports a fraction outside the axis rather than clamping it", () => {
    expect(entryFraction(95, 120, 110)).toBeCloseTo(5 / 3);
  });
});

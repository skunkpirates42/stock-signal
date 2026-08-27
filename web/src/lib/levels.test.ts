import { describe, expect, it } from "vitest";
import { entryFraction, entryLabelAnchor } from "@/lib/levels";

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

describe("entryLabelAnchor", () => {
  const cases: Array<[number, string]> = [
    [1 / 3, "middle"],
    [0, "start"],
    [0.0999, "start"],
    [0.1, "middle"],
    [0.1001, "middle"],
    [0.5, "middle"],
    [0.8999, "middle"],
    [0.9, "middle"],
    [0.9001, "end"],
    [1, "end"],
  ];

  it.each(cases)("anchors an offset of %s to %s", (offset, anchor) => {
    expect(entryLabelAnchor(offset)).toBe(anchor);
  });
});

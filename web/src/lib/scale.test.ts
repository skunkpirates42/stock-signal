import { describe, expect, it } from "vitest";
import { shareOfMax } from "@/lib/scale";

describe("shareOfMax", () => {
  it("scales each magnitude against the largest", () => {
    expect(shareOfMax([10, -5, 2.5])).toEqual([1, 0.5, 0.25]);
  });

  it("ignores sign when sizing", () => {
    expect(shareOfMax([-10, 10])).toEqual([1, 1]);
  });

  it("returns all zeroes when every value is zero", () => {
    expect(shareOfMax([0, 0])).toEqual([0, 0]);
  });

  it("returns an empty array for no values", () => {
    expect(shareOfMax([])).toEqual([]);
  });
});

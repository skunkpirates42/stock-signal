import { describe, expect, it } from "vitest";
import { netExpectancy } from "@/lib/costs";

describe("netExpectancy", () => {
  it("subtracts the round-trip cost from a positive edge", () => {
    expect(netExpectancy(3, 2)).toBe(1);
  });

  it("drives a thin edge negative", () => {
    expect(netExpectancy(3, 3.5)).toBeCloseTo(-0.5);
  });

  it("makes a negative edge worse", () => {
    expect(netExpectancy(-14.79, 2)).toBeCloseTo(-16.79);
  });

  it("returns gross when the cost is zero", () => {
    expect(netExpectancy(-14.79, 0)).toBe(-14.79);
  });
});

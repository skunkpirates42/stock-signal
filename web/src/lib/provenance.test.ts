import { describe, expect, it } from "vitest";
import { PROVISIONAL_FLOOR, isProvisional } from "@/lib/provenance";

describe("isProvisional", () => {
  it("is true below the project's evaluation floor", () => {
    expect(isProvisional(15)).toBe(true);
  });

  it("is false at the floor", () => {
    expect(isProvisional(PROVISIONAL_FLOOR)).toBe(false);
  });

  it("is false above the floor", () => {
    expect(isProvisional(150)).toBe(false);
  });
});

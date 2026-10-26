import { describe, expect, it } from "vitest";
import { PROVISIONAL_FLOOR, isProvisional, sampleWarning } from "@/lib/provenance";

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

describe("sampleWarning", () => {
  it("says no live trades have closed instead of counting zero", () => {
    const warning = sampleWarning("live", 0, 0);
    expect(warning).toBe("No live trades have closed yet. The project's evaluation floor is 50 closed trades.");
    expect(warning).not.toMatch(/\b0\b/);
  });

  it("counts a small live sample against the floor", () => {
    expect(sampleWarning("live", 12, 12)).toBe(
      "Provisional: only 12 closed trades. The project's evaluation floor is 50 closed trades — no conclusion should be drawn from this sample yet.");
  });

  it("uses the singular for one closed trade", () => {
    expect(sampleWarning("live", 1, 1)).toMatch(/^Provisional: only 1 closed trade\. /);
  });

  it("has no warning for a live sample at the floor", () => {
    expect(sampleWarning("live", PROVISIONAL_FLOOR, PROVISIONAL_FLOOR)).toBeNull();
  });

  it("says none of a blended view is live instead of counting zero", () => {
    const warning = sampleWarning("all", 5221, 0);
    expect(warning).toBe(
      "None of these 5221 closed trades are live. They are all backtest replay of a different period, not a live track record.");
  });

  it("splits a blended view into live and backtest counts", () => {
    expect(sampleWarning("all", 60, 15)).toBe(
      "Only 15 of these 60 closed trades are live; the other 45 are backtest replay of a different period. These blended figures are not a live track record — switch to the live-only view above for the real sample.");
  });

  it("has no warning for an empty blended view", () => {
    expect(sampleWarning("all", 0, 0)).toBeNull();
  });
});

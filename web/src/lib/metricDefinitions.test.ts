import { describe, expect, it } from "vitest";
import { METRIC_DEFINITIONS } from "@/lib/metricDefinitions";

describe("metric definitions", () => {
  it("covers every Overview metric a reader has had to ask about", () => {
    expect(Object.keys(METRIC_DEFINITIONS).sort()).toEqual(
      ["avgBarsHeld", "expectancy", "maxDrawdown", "profitFactor", "rMultiple"].sort(),
    );
  });

  it("gives every metric a term, a plain meaning and a formula", () => {
    for (const definition of Object.values(METRIC_DEFINITIONS)) {
      expect(definition.term.trim()).not.toBe("");
      expect(definition.meaning.trim()).not.toBe("");
      expect(definition.formula.trim()).not.toBe("");
    }
  });

  it("states profit factor as gross wins over gross losses, matching analytics/metrics.py", () => {
    expect(METRIC_DEFINITIONS.profitFactor.formula).toMatch(/won.*÷.*lost/i);
  });
});

import { describe, expect, it } from "vitest";
import { observedOrNull, formatMetricAmount } from "@/lib/metrics";

describe("formatMetricAmount", () => {
  it("signs P&L", () => expect(formatMetricAmount("realized_net_pnl", 2220.33)).toBe("+$2,220.33"));
  it("signs negative P&L", () =>
    expect(formatMetricAmount("marked_net_pnl", -12.5)).toBe("-$12.50"));
  it("signs per-session P&L", () =>
    expect(formatMetricAmount("marked_net_per_session", 26.5)).toBe("+$26.50"));
  it("renders zero P&L unsigned", () => expect(formatMetricAmount("gross_pnl", 0)).toBe("$0.00"));

  it.each([
    ["recorded_costs", 10707.82, "$10,707.82"],
    ["realized_max_drawdown", 3856.8, "$3,856.80"],
    ["marked_max_drawdown", 3881.57, "$3,881.57"],
    ["max_gross_exposure", 81443.315, "$81,443.32"],
    ["borrow_cost", 4, "$4.00"],
    ["spread_cost", 0, "$0.00"],
    ["slippage_cost", 1.5, "$1.50"],
    ["fees", 2, "$2.00"],
  ])("renders %s as an unsigned amount", (name, value, expected) =>
    expect(formatMetricAmount(name, value)).toBe(expected),
  );
});

describe("observedOrNull", () => {
  it("passes the average through when trades were observed", () =>
    expect(observedOrNull(9, -1.227)).toBe(-1.227));
  it("keeps a real zero average", () => expect(observedOrNull(3, 0)).toBe(0));
  it("is null with no observations, so zero is not shown as data", () =>
    expect(observedOrNull(0, 0)).toBeNull());
});

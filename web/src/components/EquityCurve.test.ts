import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import EquityCurve from "@/components/EquityCurve";
import EquityDataTable from "@/components/EquityDataTable";

const points = [
  { label: "start", equity: -125.5, pnl: 0 },
  { label: "2026-10-01T14:30:00Z", equity: -200.75, pnl: -75.25 },
  { label: "2026-10-02T15:00:00Z", equity: 10, pnl: 210.75 },
];

describe("EquityCurve", () => {
  it("summarizes negative equity consistently with the accessible data table", () => {
    const curve = renderToStaticMarkup(createElement(EquityCurve, { points }));
    const table = renderToStaticMarkup(createElement(EquityDataTable, { points }));
    expect(curve).toContain("Equity went from -$125.50 at start to $10.00");
    expect(curve).toContain("with a low of -$200.75 and a high of $10.00");
    expect(table).toContain('<caption class="sr-only">Equity data</caption>');
    expect(table).toContain('<td class="num">-$125.50</td>');
    expect(table).toContain('<td class="num">-$200.75</td>');
    expect(table).toContain('<td class="num">$10.00</td>');
  });

  it("defers the equity rows and chart until they are needed", () => {
    const curve = renderToStaticMarkup(createElement(EquityCurve, { points }));
    expect(curve).toContain("View equity data");
    expect(curve).not.toContain("<table");
    expect(curve).not.toContain("recharts-surface");
  });
});

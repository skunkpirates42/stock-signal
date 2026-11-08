import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import EquityCurve from "@/components/EquityCurve";

describe("EquityCurve", () => {
  it("keeps negative equity in the accessible data table consistent with its summary", () => {
    const html = renderToStaticMarkup(
      createElement(EquityCurve, {
        points: [
          { label: "start", equity: -125.5, pnl: 0 },
          { label: "2026-10-01T14:30:00Z", equity: -200.75, pnl: -75.25 },
          { label: "2026-10-02T15:00:00Z", equity: 10, pnl: 210.75 },
        ],
      }),
    );
    expect(html).toContain('<caption class="sr-only">Equity data</caption>');
    expect(html).toContain('<td class="num">-$125.50</td>');
    expect(html).toContain('<td class="num">-$200.75</td>');
    expect(html).toContain('<td class="num">$10.00</td>');
    expect(html).toContain("Equity went from -$125.50 at start to $10.00");
    expect(html).toContain("with a low of -$200.75 and a high of $10.00");
  });
});

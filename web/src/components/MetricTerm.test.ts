import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import MetricTerm from "@/components/MetricTerm";
import StatTile from "@/components/StatTile";
import { METRIC_DEFINITIONS } from "@/lib/metricDefinitions";

function render() {
  return renderToStaticMarkup(createElement(MetricTerm, METRIC_DEFINITIONS.profitFactor));
}

describe("MetricTerm", () => {
  it("is a real button, so keyboard and touch users can open it, not a hover-only title", () => {
    const html = render();
    expect(html).toMatch(/<button type="button"[^>]*>Profit factor<\/button>/);
    expect(html).not.toContain("title=");
  });

  it("starts closed and points the button at the definition it controls", () => {
    const html = render();
    const controls = /aria-controls="([^"]+)"/.exec(html)?.[1];
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain(`id="${controls}"`);
    expect(html).toMatch(/popover="manual"/);
  });

  it("carries both the plain meaning and the formula", () => {
    const html = render();
    expect(html).toContain("Dollars the winners made");
    expect(html).toContain("total $ won by winning trades ÷ total $ lost by losing trades");
  });
});

describe("StatTile with a definition", () => {
  it("renders its label as a MetricTerm button", () => {
    const html = renderToStaticMarkup(
      createElement(StatTile, {
        label: "Profit factor",
        value: "1.08",
        definition: METRIC_DEFINITIONS.profitFactor,
      }),
    );
    expect(html).toMatch(/<div class="stat-tile-label"><span class="metric-term">/);
  });

  it("keeps a plain label without one", () => {
    const html = renderToStaticMarkup(createElement(StatTile, { label: "Trades", value: "3" }));
    expect(html).toContain('<div class="stat-tile-label">Trades</div>');
  });
});

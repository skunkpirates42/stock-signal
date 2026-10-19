import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import CostAdjustedExpectancy from "./CostAdjustedExpectancy";

const render = (recordedExpectancy: number | null) =>
  renderToStaticMarkup(createElement(CostAdjustedExpectancy, { recordedExpectancy }));

describe("CostAdjustedExpectancy", () => {
  it("shows dashes and says why when there are no closed trades", () => {
    const html = render(null);
    expect(html).not.toContain("$0.00");
    expect(html).not.toContain("-$2.00");
    expect(html).toContain("No closed trades yet");
  });

  it("subtracts the extra cost from a recorded expectancy", () => {
    const html = render(-8.93);
    expect(html).toContain('tone-negative">-$8.93');
    expect(html).toContain('tone-negative">-$10.93');
  });
});

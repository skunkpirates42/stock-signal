import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import WinLossCard from "./WinLossCard";

const render = (props: Parameters<typeof WinLossCard>[0]) => renderToStaticMarkup(createElement(WinLossCard, props));

describe("WinLossCard", () => {
  it("shows unknown figures as dashes, not zeros", () => {
    const html = render({ nWins: 0, nLosses: 0, winRate: null, avgWin: null, avgLoss: null });
    expect(html).not.toContain("$0.00");
    expect(html).not.toContain("0.0%");
    expect(html.match(/—/g)).toHaveLength(3);
  });

  it("colors averages by sign", () => {
    const html = render({ nWins: 3, nLosses: 2, winRate: 0.6, avgWin: 51.05, avgLoss: -31.25 });
    expect(html).toContain('class="num tone-positive">+$51.05');
    expect(html).toContain('class="num tone-negative">-$31.25');
  });
});

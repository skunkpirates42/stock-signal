import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RatioBar from "./RatioBar";

const render = (left: number, right: number) =>
  renderToStaticMarkup(createElement(RatioBar, { left, right, leftLabel: "wins", rightLabel: "losses" }));

describe("RatioBar", () => {
  it("draws an empty track, not a full loss bar, when both sides are zero", () => {
    expect(render(0, 0)).toContain('class="ratio-track ratio-track-empty"');
  });

  it("keeps the loss-colored track once there is anything to compare", () => {
    expect(render(0, 3)).toContain('class="ratio-track"');
    expect(render(0, 3)).not.toContain("ratio-track-empty");
  });
});

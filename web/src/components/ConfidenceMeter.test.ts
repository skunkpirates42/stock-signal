import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ConfidenceMeter from "./ConfidenceMeter";
import { CONFIDENCE_THRESHOLD } from "@/lib/indicators";
import { formatPercent } from "@/lib/format";

const textOf = (confidence: number) =>
  renderToStaticMarkup(createElement(ConfidenceMeter, { confidence }))
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ");

describe("ConfidenceMeter", () => {
  it("names the value and the threshold in text, not only in the drawn marker", () => {
    expect(textOf(0.7)).toContain(`Confidence ${formatPercent(0.7)}`);
    expect(textOf(0.7)).toContain(`threshold ${formatPercent(CONFIDENCE_THRESHOLD)}`);
  });
});

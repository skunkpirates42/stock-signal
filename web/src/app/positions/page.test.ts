import { expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
vi.mock("@/components/PositionsView", () => ({ default: () => null }));
import Page from "./page";
it("explains broker ownership independently of prices", () => {
  const html = renderToStaticMarkup(createElement(Page));
  expect(html).toContain("Market prices do not establish broker holdings");
  expect(html).toContain("unknown provenance");
});

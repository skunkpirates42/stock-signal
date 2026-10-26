import { afterEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import Page from "./page";

afterEach(() => vi.unstubAllGlobals());

function renderPage() {
  return renderToStaticMarkup(createElement(Page));
}

describe("system page", () => {
  it("renders without touching the network", () => {
    const fetch = vi.fn(() => {
      throw new Error("no network on /system");
    });
    vi.stubGlobal("fetch", fetch);
    renderPage();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("shows unavailable and missing values as Unavailable with their reasons", () => {
    const html = renderPage();
    expect(html).toContain('<span class="value-reason">Fees were not saved.</span>');
    expect(html).toContain('<span class="value-reason">No saved metric.</span>');
    expect(html).not.toMatch(/Unavailable[^<]*\$0\.00/);
  });

  it("shows the disclosure both closed and open", () => {
    const html = renderPage();
    expect(html).toMatch(/<details class="disclosure card"><summary>Disclosure, closed/);
    expect(html).toMatch(/<details open="" class="disclosure card"><summary>Disclosure, open/);
  });

  it("shows a table's empty state", () => {
    expect(renderPage()).toContain('class="data-table-empty">No rows.</td>');
  });
});

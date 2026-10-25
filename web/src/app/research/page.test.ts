import { describe, expect, it, vi } from "vitest";
import { Children, isValidElement, type ReactNode } from "react";

const NEXT_CURSOR = "123e4567-e89b-12d3-a456-426614174000";

function savedResult(id: string, variant: string, windowName: string, pnl: { availability: "available"; value: number } | { availability: "unavailable" }, synthetic = false) {
  const window = windowName === "development"
    ? { name: "development", role: "development", start: "2026-03-01T00:00:00Z", end_exclusive: "2026-07-01T00:00:00Z" }
    : { name: "holdout", role: "holdout", start: "2026-07-01T00:00:00Z", end_exclusive: "2026-09-01T00:00:00Z" };
  const observation = pnl.availability === "available"
    ? { availability: "available", value: pnl.value, reason: null, detail: null }
    : { availability: "unavailable", value: null, reason: "not_recorded", detail: "Not saved" };
  return { id, run_id: `${id}-run`, window, variant, provenance: { retrospective: true, synthetic }, accounting: { coverage: "incomplete" },
    metrics: { realized_net_pnl: { observation, unit: "USD", basis: "Saved value", source_pointer: "/comparison" } } };
}

vi.mock("@/lib/demo", () => ({
  isOpaqueDemoId: vi.fn(() => true),
  getResearchResults: vi.fn(async () => ({
    data: {
      results: [
        savedResult("base-dev", "baseline", "development", { availability: "available", value: 2220.33 }),
        savedResult("base-hold", "baseline", "holdout", { availability: "unavailable" }),
        savedResult("rvol-dev", "rvol", "development", { availability: "available", value: -1111.54 }, true),
      ],
      next_cursor: NEXT_CURSOR,
    },
    warnings: ["Saved-source research catalog only; it does not authorize execution or replay.", "Catalog only."],
  })),
}));

import Page from "./page";
import { getResearchResults, isOpaqueDemoId } from "@/lib/demo";

function rendered(node: unknown): unknown {
  if (!isValidElement<{ children?: unknown }>(node)) return node;
  if (typeof node.type === "function" && ["ResearchComparisonTable", "PageHeader"].includes(node.type.name)) {
    return rendered((node.type as (props: unknown) => unknown)(node.props));
  }
  return node;
}

function textOf(node: unknown): string {
  const element = rendered(node);
  if (typeof element === "string" || typeof element === "number") return String(element);
  if (!isValidElement<{ children?: unknown }>(element)) return "";
  return Children.toArray(element.props.children as ReactNode).map(textOf).join(" ");
}

function hrefs(node: unknown): string[] {
  const element = rendered(node);
  if (!isValidElement<{ children?: unknown; href?: string }>(element)) return [];
  const own = element.props.href ? [element.props.href] : [];
  return [...own, ...Children.toArray(element.props.children as ReactNode).flatMap(hrefs)];
}

function normalizedText(node: unknown): string {
  return textOf(node).replace(/\s+/g, " ");
}

describe("research page", () => {
  it("compares saved results by variant and window and links each cell to its result", async () => {
    const page = await Page({ searchParams: Promise.resolve({}) });
    const text = normalizedText(page);
    expect(text).toContain("+$2,220.33");
    expect(text).toContain("-$1,111.54");
    expect(text).toContain("Unavailable");
    expect(text).not.toContain("$0.00");
    expect(text).toContain("No saved result");
    expect(text).toContain("Synthetic correctness");
    expect(text).toContain("Mar 1 – Jul 1, 2026");
    expect(text).toContain("inclusive");
    expect(text).toContain("Accounting coverage is incomplete for every result here.");
    expect(hrefs(page).filter((href) => href.startsWith("/research/"))).toEqual(["/research/base-dev", "/research/base-hold", "/research/rvol-dev"]);
  });

  it("keeps the scope note, extra warnings and page count", async () => {
    const text = normalizedText(await Page({ searchParams: Promise.resolve({}) }));
    expect(text).toContain("Catalog only.");
    expect(text).not.toContain("Saved-source research catalog only");
    expect(text).toContain("do not authorize replay");
    expect(text).toContain("3 results on this page");
  });

  it("says the table covers this page only when there is a next page", async () => {
    const page = await Page({ searchParams: Promise.resolve({}) });
    expect(normalizedText(page)).toContain("this page only");
    expect(hrefs(page)).toContain(`/research?cursor=${NEXT_CURSOR}`);
  });

  it("omits the next-page note on the last page", async () => {
    vi.mocked(getResearchResults).mockResolvedValueOnce({ schema_version: 1, data: { results: [], next_cursor: null }, warnings: [] });
    const text = normalizedText(await Page({ searchParams: Promise.resolve({}) }));
    expect(text).not.toContain("this page only");
    expect(text).toContain("No saved results are indexed");
  });

  it("treats an empty cursor as an unknown research page", async () => {
    vi.mocked(isOpaqueDemoId).mockReturnValueOnce(false);
    await expect(Page({ searchParams: Promise.resolve({ cursor: "" }) })).rejects.toMatchObject({
      digest: "NEXT_HTTP_ERROR_FALLBACK;404",
    });
  });
});

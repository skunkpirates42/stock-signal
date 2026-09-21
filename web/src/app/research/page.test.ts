import { describe, expect, it, vi } from "vitest";
import { Children, isValidElement, type ReactNode } from "react";

vi.mock("@/lib/demo", () => ({
  isOpaqueDemoId: vi.fn(() => true),
  getResearchResults: vi.fn(async () => ({ data: { results: [{ id: "saved-result", run_id: "saved-run", window: { name: "fixture", role: "fixture", start: "2026-01-01T00:00:00Z", end_exclusive: "2026-01-02T00:00:00Z" }, variant: "baseline", provenance: { retrospective: false, synthetic: true }, accounting: { coverage: "incomplete" }, metrics: { realized_net_pnl: { observation: { availability: "available", value: 0 }, unit: "USD", basis: "Synthetic saved value", source_pointer: "/comparison" } } }], next_cursor: "123e4567-e89b-12d3-a456-426614174000" }, warnings: ["Catalog only."] })),
}));

import Page from "./page";
import { isOpaqueDemoId } from "@/lib/demo";

function textOf(node: unknown): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (!isValidElement<{ children?: unknown }>(node)) return "";
  return Children.toArray(node.props.children as ReactNode).map(textOf).join(" ");
}

function hasHref(node: unknown, href: string): boolean {
  if (!isValidElement<{ children?: unknown; href?: string }>(node)) return false;
  if (node.props.href === href) return true;
  return Children.toArray(node.props.children as ReactNode).some((child) => hasHref(child, href));
}

describe("research page", () => {
  it("labels synthetic saved results and links by the opaque result ID", async () => {
    const page = await Page({ searchParams: Promise.resolve({}) });
    expect(textOf(page)).toContain("Synthetic correctness");
    expect(hasHref(page, "/runs/saved-result")).toBe(true);
    expect(textOf(page)).toContain("Catalog only.");
    expect(textOf(page)).toContain("inclusive");
    expect(textOf(page)).toContain("results on this page");
    expect(hasHref(page, "/research?cursor=123e4567-e89b-12d3-a456-426614174000")).toBe(true);
  });

  it("treats an empty cursor as an unknown research page", async () => {
    vi.mocked(isOpaqueDemoId).mockReturnValueOnce(false);
    await expect(Page({ searchParams: Promise.resolve({ cursor: "" }) })).rejects.toMatchObject({
      digest: "NEXT_HTTP_ERROR_FALLBACK;404",
    });
  });
});

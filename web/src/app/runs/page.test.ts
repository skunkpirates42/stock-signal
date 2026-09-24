import { describe, expect, it, vi } from "vitest";
import { Children, isValidElement, type ReactNode } from "react";

const RUN_ID = "123e4567-e89b-12d3-a456-426614174000";
vi.mock("@/lib/jobs", () => ({ getJobs: vi.fn(async () => ({ data: { runs: [{
  run_id: RUN_ID, state: "failed", attempt: { availability: "available", value: 2 },
  created_at: { availability: "available", value: "2026-09-24T12:00:00Z" },
}], next_cursor: RUN_ID }, warnings: [] })) }));

import Page from "./page";

function content(node: unknown): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (!isValidElement<{ children?: unknown; href?: string }>(node)) return "";
  return [node.props.href, ...Children.toArray(node.props.children as ReactNode)].map(content).join(" ");
}

describe("run history", () => {
  it("links job IDs and shows the persisted failed attempt", async () => {
    const page = await Page({ searchParams: Promise.resolve({}) });
    const text = content(page);
    expect(text).toMatch(/failed\s+· attempt\s+2/);
    expect(text).toContain(`/runs/${RUN_ID}`);
    expect(text).toContain(`/runs?cursor=${RUN_ID}`);
  });
});

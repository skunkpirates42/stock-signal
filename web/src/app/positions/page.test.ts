import { describe, expect, it, vi } from "vitest";
import type { Trade } from "@/lib/types";

vi.mock("@/lib/api", () => ({
  getOpenPositions: vi.fn(async (source: string) => [{ id: source === "live" ? 1 : 2, source }]),
  getTrades: vi.fn(async () => []),
}));
vi.mock("@/components/OpenPositions", () => ({ default: () => null }));
vi.mock("@/components/FillsTable", () => ({ default: () => null }));
vi.mock("@/components/ScopeNote", () => ({ default: () => null }));
import Page from "./page";
import OpenPositions from "@/components/OpenPositions";
import { getOpenPositions } from "@/lib/api";
import { Children, isValidElement } from "react";

describe("positions scope", () => {
  it("includes unknown exposure in the default view", async () => {
    const page = await Page({ searchParams: Promise.resolve({}) });
    const list = Children.toArray(page.props.children).find(
      child => isValidElement(child) && child.type === OpenPositions,
    );
    if (!isValidElement<{ positions: Trade[] }>(list)) throw new Error("Missing positions");
    expect(list.props.positions.map(p => p.source)).toEqual(["live", "unknown"]);
    expect(getOpenPositions).not.toHaveBeenCalledWith("all");
  });
});

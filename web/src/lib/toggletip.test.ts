import { describe, expect, it } from "vitest";
import { CLOSED, nextToggletipState, toggletipPosition } from "@/lib/toggletip";

const hoverOpen = nextToggletipState(CLOSED, "hover");
const pinnedOpen = nextToggletipState(CLOSED, "toggle");

describe("toggletip state", () => {
  it("opens on hover and on keyboard focus without pinning", () => {
    expect(hoverOpen).toEqual({ open: true, pinned: false });
    expect(nextToggletipState(CLOSED, "focus")).toEqual({ open: true, pinned: false });
  });

  it("closes when the pointer leaves, unless a click pinned it open", () => {
    expect(nextToggletipState(hoverOpen, "unhover")).toEqual(CLOSED);
    expect(nextToggletipState(pinnedOpen, "unhover")).toEqual(pinnedOpen);
  });

  it("pins open on the first click or tap, even after hover opened it, and closes on the next", () => {
    expect(pinnedOpen).toEqual({ open: true, pinned: true });
    expect(nextToggletipState(hoverOpen, "toggle")).toEqual({ open: true, pinned: true });
    expect(nextToggletipState(pinnedOpen, "toggle")).toEqual(CLOSED);
  });

  it("closes on blur, Escape, an outside click or scroll, pinned or not", () => {
    for (const state of [hoverOpen, pinnedOpen]) {
      expect(nextToggletipState(state, "blur")).toEqual(CLOSED);
      expect(nextToggletipState(state, "dismiss")).toEqual(CLOSED);
    }
  });
});

describe("toggletip position", () => {
  const viewport = { width: 1200, height: 800 };
  const panel = { width: 280, height: 120 };

  it("sits directly under the label, aligned to its left edge", () => {
    const anchor = { top: 100, bottom: 120, left: 300 };
    expect(toggletipPosition(anchor, panel, viewport)).toEqual({ top: 120, left: 300 });
  });

  it("keeps a 16px gutter from the right edge on a narrow screen", () => {
    const anchor = { top: 100, bottom: 120, left: 200 };
    expect(toggletipPosition(anchor, panel, { width: 390, height: 800 }).left).toBe(94);
  });

  it("never pushes past the left gutter when the panel is wider than the screen", () => {
    const anchor = { top: 100, bottom: 120, left: 20 };
    expect(
      toggletipPosition(anchor, { width: 400, height: 120 }, { width: 320, height: 800 }).left,
    ).toBe(16);
  });

  it("flips above the label when there is no room below", () => {
    const anchor = { top: 700, bottom: 720, left: 300 };
    expect(toggletipPosition(anchor, panel, viewport).top).toBe(580);
  });
});

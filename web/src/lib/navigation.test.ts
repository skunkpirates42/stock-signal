import { describe, expect, it } from "vitest";
import { isActiveRailLink } from "@/lib/navigation";

describe("isActiveRailLink", () => {
  it("matches the exact path", () => expect(isActiveRailLink("/signals", "/signals")).toBe(true));
  it("highlights Research on a saved result", () => expect(isActiveRailLink("/research/abc", "/research")).toBe(true));
  it("highlights Run history on a job", () => expect(isActiveRailLink("/runs/abc", "/runs")).toBe(true));
  it("keeps saved results out of Run history", () => expect(isActiveRailLink("/research/abc", "/runs")).toBe(false));
  it("does not treat New run as a prefix of Run history", () => expect(isActiveRailLink("/runs/abc", "/run")).toBe(false));
  it("does not highlight Overview on every page", () => expect(isActiveRailLink("/research/abc", "/")).toBe(false));
});

import { afterEach, expect, it, vi } from "vitest";
import { GET } from "./route";

afterEach(() => vi.unstubAllGlobals());
it("proxies prices without allowing browser caching", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ prices: {} })));
  const response = await GET();
  expect(response.status).toBe(200);
  expect(response.headers.get("Cache-Control")).toBe("no-store");
  expect(await response.json()).toEqual({ prices: {} });
});
it("returns a safe failure without exposing upstream errors", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("private upstream detail")));
  const response = await GET();
  expect(response.status).toBe(503);
  expect(await response.json()).toEqual({ error: "Prices unavailable" });
});

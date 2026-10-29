import { afterEach, expect, it, vi } from "vitest";
import { GET } from "./route";
afterEach(() => vi.unstubAllGlobals());
it("uses only the fixed read-only no-store endpoint", async () => {
  const fetch = vi.fn().mockResolvedValue(Response.json({ accounts: [] }));
  vi.stubGlobal("fetch", fetch);
  const response = await GET();
  expect(fetch.mock.calls[0][0]).toMatch(/\/api\/position-state$/);
  expect(fetch.mock.calls[0][1].cache).toBe("no-store");
  expect(response.headers.get("Cache-Control")).toBe("no-store");
  expect(await response.json()).toEqual({ accounts: [] });
});
it("sanitizes upstream failure and does not return a healthy empty account", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("private broker detail")));
  const response = await GET();
  expect(response.status).toBe(503);
  expect(response.headers.get("Cache-Control")).toBe("no-store");
  expect(await response.json()).toEqual({ error: "Position state unavailable" });
});

import { afterEach, expect, it, vi } from "vitest";
import { GET } from "./route";
import { GET as getMarket } from "../market-status/route";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
it("proxies prices without allowing browser caching", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ prices: {} })));
  const response = await GET();
  expect(response.status).toBe(200);
  expect(response.headers.get("Cache-Control")).toBe("no-store");
  expect(await response.json()).toEqual({ prices: {} });
});
it("returns a safe failure without exposing upstream errors", async () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("private upstream detail")));
  const response = await GET();
  expect(response.status).toBe(503);
  expect(await response.json()).toEqual({ error: "Market data unavailable" });
  expect(log).toHaveBeenCalledTimes(1);
  expect(log.mock.calls[0][0]).toMatch(
    /web_upstream_failed path=\/api\/position-prices error=Error$/,
  );
  expect(log.mock.calls[0][0]).not.toContain("private upstream detail");
});

it("proxies the shared market clock without requesting prices", async () => {
  const fetch = vi.fn().mockResolvedValue(Response.json({ market_open: false }));
  vi.stubGlobal("fetch", fetch);
  const response = await getMarket();
  expect(fetch.mock.calls[0][0]).toMatch(/\/api\/market-status$/);
  expect(await response.json()).toEqual({ market_open: false });
  expect(response.headers.get("Cache-Control")).toBe("no-store");
});

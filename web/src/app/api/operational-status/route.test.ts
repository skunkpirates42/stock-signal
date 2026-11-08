import { afterEach, expect, it, vi } from "vitest";
import { GET } from "./route";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it("fetches parsed status with a timeout and no-store caching", async () => {
  const status = { latest_bar: null, runtime: [], unresolved_orders: [] };
  const fetchResponse = vi.fn().mockResolvedValue(Response.json(status));
  vi.stubGlobal("fetch", fetchResponse);
  const response = await GET();
  expect(fetchResponse).toHaveBeenCalledWith(expect.stringMatching(/\/api\/status$/), {
    cache: "no-store",
    signal: expect.any(AbortSignal),
  });
  expect(response.headers.get("Cache-Control")).toBe("no-store");
  expect(await response.json()).toEqual(status);
});

it.each(["transport", "http", "schema", "json", "timeout"])(
  "records a safe %s failure",
  async (category) => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const fetchResponse = vi.fn();
    if (category === "transport")
      fetchResponse.mockRejectedValue(new TypeError("private credentials"));
    if (category === "timeout")
      fetchResponse.mockRejectedValue(new DOMException("private URL", "TimeoutError"));
    if (category === "http")
      fetchResponse.mockResolvedValue(new Response("private payload", { status: 503 }));
    if (category === "schema")
      fetchResponse.mockResolvedValue(Response.json({ private: "payload" }));
    if (category === "json") fetchResponse.mockResolvedValue(new Response("private invalid JSON"));
    vi.stubGlobal("fetch", fetchResponse);
    const response = await GET();
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ error: "Status update unavailable" });
    expect(log.mock.calls).toEqual([
      ["web_failure", { resource: "operational-status", category, reference: null }],
    ]);
  },
);

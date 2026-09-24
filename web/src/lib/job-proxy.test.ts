import { afterEach, describe, expect, it, vi } from "vitest";
import { cancelJob, submitJob } from "@/lib/job-proxy";

const RUN_ID = "123e4567-e89b-12d3-a456-426614174000";
const requestBody = { strategy_id: "stock-signal", dataset_id: "dataset", window_id: "window",
  cost_profile_id: "base-v2", idempotency_key: "click-0001" };

function request(path: string, body: unknown, origin = "http://localhost:3000") {
  return new Request(`http://localhost:3000${path}`, { method: "POST",
    headers: { Host: "localhost:3000", Origin: origin, "Content-Type": "application/json" },
    body: JSON.stringify(body) });
}

afterEach(() => vi.restoreAllMocks());

describe("local run mutation proxy", () => {
  it("rejects foreign origins and host rebinding before contacting Flask", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    expect((await submitJob(request("/api/demo/v1/runs", requestBody, "http://evil.example"))).status).toBe(403);
    const rebound = new Request("http://evil.example/api/demo/v1/runs", { method: "POST",
      headers: { Host: "evil.example", Origin: "http://evil.example", "Content-Type": "application/json" },
      body: JSON.stringify(requestBody) });
    expect((await submitJob(rebound)).status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards only a bounded catalog-ID request and preserves conflict codes", async () => {
    const fetchMock = vi.fn(async () => Response.json({ error: { code: "idempotency_conflict", message: "Used key" } },
      { status: 409 }));
    vi.stubGlobal("fetch", fetchMock);
    const response = await submitJob(request("/api/demo/v1/runs", requestBody));
    expect(response.status).toBe(409);
    expect((await response.json()).error.code).toBe("idempotency_conflict");
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:8000/api/demo/v1/runs", expect.objectContaining({
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(requestBody),
    }));
    expect((await submitJob(request("/api/demo/v1/runs", { ...requestBody, dataset_path: "/tmp/bars" }))).status).toBe(400);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("accepts the incoming local Host and Origin when Next normalizes request.url", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ data: { status: { run_id: RUN_ID } } }, { status: 202 })));
    const normalized = new Request("http://internal-next:3100/api/demo/v1/runs", { method: "POST",
      headers: { Host: "127.0.0.1:3100", Origin: "http://127.0.0.1:3100", "Content-Type": "application/json" },
      body: JSON.stringify(requestBody) });
    expect((await submitJob(normalized)).status).toBe(202);
  });

  it("cancels only an opaque run with an empty JSON body", async () => {
    const fetchMock = vi.fn(async (url: string, init: RequestInit) => {
      expect(url).toContain("/runs/");
      expect(init.method).toBe("POST");
      return Response.json({ data: { status: { state: "cancel_requested" } } });
    });
    vi.stubGlobal("fetch", fetchMock);
    expect((await cancelJob(request("/cancel", {}), "../other")).status).toBe(404);
    expect((await cancelJob(request("/cancel", { extra: true }), RUN_ID)).status).toBe(400);
    expect((await cancelJob(request("/cancel", {}), RUN_ID)).status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(`http://127.0.0.1:8000/api/demo/v1/runs/${RUN_ID}/cancel`);
  });

  it("does not forward HTML or upstream faults to the browser", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("internal traceback", { status: 500, headers: { "Content-Type": "text/html" } })));
    const response = await submitJob(request("/api/demo/v1/runs", requestBody));
    expect(response.status).toBe(502);
    expect(JSON.stringify(await response.json())).not.toContain("traceback");
  });
});

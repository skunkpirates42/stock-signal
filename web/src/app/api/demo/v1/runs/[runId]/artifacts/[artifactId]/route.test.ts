import { afterEach, expect, it, vi } from "vitest";
import { GET } from "./route";

const RUN_ID = "123e4567-e89b-12d3-a456-426614174000";
const ARTIFACT_ID = "223e4567-e89b-12d3-a456-426614174000";
const UPSTREAM_PATH = `/api/demo/v1/runs/${RUN_ID}/artifacts/${ARTIFACT_ID}`;

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function get() {
  return GET(new Request(`http://localhost:3000${UPSTREAM_PATH}`), {
    params: Promise.resolve({ runId: RUN_ID, artifactId: ARTIFACT_ID }),
  });
}

it("logs an unreachable upstream and still returns a bodiless 502", async () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("t", "TimeoutError")));
  const response = await get();
  expect(response.status).toBe(502);
  expect(await response.text()).toBe("");
  expect(log.mock.calls[0][0]).toContain(
    `web_upstream_failed path=${UPSTREAM_PATH} error=TimeoutError`,
  );
});

it("logs an upstream server error by status", async () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("trace", { status: 500 })));
  const response = await get();
  expect(response.status).toBe(502);
  expect(log.mock.calls[0][0]).toMatch(/ status=500$/);
});

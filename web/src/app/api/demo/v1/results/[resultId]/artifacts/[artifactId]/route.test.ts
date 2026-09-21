import { afterEach, describe, expect, it, vi } from "vitest";
import { GET } from "./route";

const RESULT_ID = "11111111-1111-4111-8111-111111111111";
const ARTIFACT_ID = "22222222-2222-4222-8222-222222222222";
const context = (resultId = RESULT_ID, artifactId = ARTIFACT_ID) => ({
  params: Promise.resolve({ resultId, artifactId }),
});

afterEach(() => vi.unstubAllGlobals());

describe("saved artifact proxy", () => {
  it("serves bounded allowlisted bytes without exposing the upstream address", async () => {
    const upstream = vi.fn(async () => new Response("saved", {
      headers: { "Content-Type": "text/plain; charset=utf-8", "Content-Length": "5" },
    }));
    vi.stubGlobal("fetch", upstream);

    const response = await GET(new Request("http://example.test/api/demo"), context());

    expect(response.status).toBe(200);
    expect(await response.text()).toBe("saved");
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("x-content-type-options")).toBe("nosniff");
    expect(upstream).toHaveBeenCalledWith(
      `http://127.0.0.1:8000/api/demo/v1/results/${RESULT_ID}/artifacts/${ARTIFACT_ID}`,
      { cache: "no-store", redirect: "manual" },
    );
  });

  it("rejects malformed opaque IDs before contacting Flask", async () => {
    const upstream = vi.fn();
    vi.stubGlobal("fetch", upstream);
    expect((await GET(new Request("http://example.test"), context("../secret"))).status).toBe(404);
    expect(upstream).not.toHaveBeenCalled();
  });

  it.each([404, 413])("preserves an upstream %i response", async (status) => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status })));
    expect((await GET(new Request("http://example.test"), context())).status).toBe(status);
  });

  it("rejects unexpected content types", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>", {
      headers: { "Content-Type": "text/html", "Content-Length": "6" },
    })));
    expect((await GET(new Request("http://example.test"), context())).status).toBe(502);
  });

  it("rejects declared and streamed content beyond the fixed bound", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("x", {
      headers: { "Content-Type": "text/plain", "Content-Length": String(1024 * 1024 + 1) },
    })));
    expect((await GET(new Request("http://example.test"), context())).status).toBe(413);

    vi.stubGlobal("fetch", vi.fn(async () => new Response("too long", {
      headers: { "Content-Type": "text/plain", "Content-Length": "3" },
    })));
    expect((await GET(new Request("http://example.test"), context())).status).toBe(413);
  });
});

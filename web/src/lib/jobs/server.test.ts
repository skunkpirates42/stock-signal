import { afterEach, describe, expect, it, vi } from "vitest";
import { getJob, getJobs, getReplayCatalog } from "@/lib/jobs/server";

const RUN_ID = "123e4567-e89b-12d3-a456-426614174000";
const catalog = {
  strategy: { id: "stock-signal", label: "Six-vote engine", editable_fields: [] },
  datasets: [],
  cost_profiles: [],
};

afterEach(() => vi.unstubAllGlobals());

describe("job reads", () => {
  it("reads the replay catalog through its response contract without following redirects", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json({ schema_version: 1, data: catalog, warnings: [] }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getReplayCatalog()).resolves.toEqual({
      schema_version: 1,
      data: catalog,
      warnings: [],
    });
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:8000/api/demo/v1/replay-catalog", {
      cache: "no-store",
      redirect: "manual",
      signal: expect.any(AbortSignal),
    });
  });

  it("rejects catalog strategy edits instead of exposing unsupported controls", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({
          schema_version: 1,
          warnings: [],
          data: { ...catalog, strategy: { ...catalog.strategy, editable_fields: ["threshold"] } },
        }),
      ),
    );

    await expect(getReplayCatalog()).rejects.toThrow("editable_fields: expected empty array");
  });

  it("rejects a malformed job record at the fetch boundary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({
          schema_version: 1,
          warnings: [],
          data: { runs: [{ record_type: "result" }], next_cursor: null },
        }),
      ),
    );

    await expect(getJobs()).rejects.toThrow("record_type: expected status");
  });

  it("rejects invalid job IDs and cursors before fetching", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    expect(() => getJob("not-an-id")).toThrow("Demo job was not found");
    expect(() => getJobs("")).toThrow("Demo cursor was not found");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects upstream redirects instead of treating them as job data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 302, headers: { Location: "/login" } })),
    );

    await expect(getJob(RUN_ID)).rejects.toThrow("responded 302");
  });
});

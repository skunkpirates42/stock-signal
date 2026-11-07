import { afterEach, describe, expect, it, vi } from "vitest";
import { queueReplayRun, requestRunCancel, RUN_REQUEST_TIMEOUT_MS } from "@/lib/runRequests";

const RUN_ID = "123e4567-e89b-12d3-a456-426614174000";
const choices = {
  strategy_id: "stock-signal",
  dataset_id: "dataset",
  window_id: "window",
  cost_profile_id: "base-v2",
  idempotency_key: "click-0001",
};

function respondWith(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("queueReplayRun", () => {
  it("posts the choices to the local proxy and returns the queued run ID", async () => {
    const fetchMock = respondWith(202, { data: { status: { run_id: RUN_ID } } });
    expect(await queueReplayRun(choices)).toEqual({ ok: true, runId: RUN_ID });
    expect(fetchMock).toHaveBeenCalledWith("/api/demo/v1/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(choices),
      signal: expect.any(AbortSignal),
    });
  });

  it("explains a known rejection and keeps the key so a retry finds the same run", async () => {
    respondWith(503, { error: { code: "job_store_busy" } });
    expect(await queueReplayRun(choices)).toEqual({
      ok: false,
      message: "The local job store is busy. Retry with the same choices.",
      keyRejected: false,
    });
  });

  it("flags an idempotency conflict so the form drops the used key", async () => {
    respondWith(409, { error: { code: "idempotency_conflict" } });
    const outcome = await queueReplayRun(choices);
    expect(outcome).toMatchObject({ ok: false, keyRejected: true });
  });

  it.each(["something_new", "toString", "__proto__"])(
    "explains an unknown error code: %s",
    async (code) => {
      respondWith(400, { error: { code } });
      expect(await queueReplayRun(choices)).toMatchObject({
        ok: false,
        message: "The run request was rejected. Check the approved choices and retry.",
      });
    },
  );

  it.each([
    null,
    [],
    {},
    { data: [] },
    { data: { status: {} } },
    { data: { status: { run_id: 42 } } },
    ...[
      "",
      "queued-id",
      "../runs",
      "javascript:alert(1)",
      `${RUN_ID}/cancel`,
      "a".repeat(1024),
    ].map((run_id) => ({ data: { status: { run_id } } })),
  ])("treats invalid success shapes and run IDs as unreadable: %j", async (body) => {
    respondWith(202, body);
    expect(await queueReplayRun(choices)).toMatchObject({
      ok: false,
      message: "The submission response could not be read. Retry to look up the same run.",
    });
  });

  it.each([null, [], {}, { error: [] }, { error: { code: false } }])(
    "keeps the key when the rejection body is invalid: %j",
    async (body) => {
      respondWith(409, body);
      expect(await queueReplayRun(choices)).toMatchObject({
        ok: false,
        keyRejected: false,
        message: "The submission response could not be read. Retry to look up the same run.",
      });
    },
  );

  it.each([202, 409])("keeps the key for malformed JSON with HTTP %i", async (status) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("invalid JSON", { status })),
    );
    expect(await queueReplayRun(choices)).toMatchObject({
      ok: false,
      keyRejected: false,
      message: "The submission response could not be read. Retry to look up the same run.",
    });
  });

  it("reports an unreachable service without throwing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      }),
    );
    expect(await queueReplayRun(choices)).toMatchObject({
      ok: false,
      keyRejected: false,
      message: expect.stringContaining("The run may still have been queued"),
    });
  });

  it.each(["headers", "success body", "error body"])(
    "bounds stalled %s, aborts the request, and allows a same-key retry",
    async (stage) => {
      vi.useFakeTimers();
      const stalledBody = () =>
        new Response(new ReadableStream(), { status: stage === "error body" ? 409 : 202 });
      const fetchMock = vi
        .fn<typeof fetch>()
        .mockImplementationOnce(() =>
          stage === "headers" ? new Promise(() => {}) : Promise.resolve(stalledBody()),
        )
        .mockResolvedValueOnce(
          Response.json({ data: { status: { run_id: RUN_ID } } }, { status: 202 }),
        );
      vi.stubGlobal("fetch", fetchMock);
      const pending = queueReplayRun(choices);
      await vi.advanceTimersByTimeAsync(RUN_REQUEST_TIMEOUT_MS);
      expect(await pending).toEqual({
        ok: false,
        keyRejected: false,
        message:
          "The submission timed out. The run may still have been queued. Retry to look up the same run.",
      });
      expect(fetchMock.mock.calls[0][1]?.signal?.aborted).toBe(true);
      expect(await queueReplayRun(choices)).toEqual({ ok: true, runId: RUN_ID });
      expect(fetchMock.mock.calls[1][1]?.body).toBe(fetchMock.mock.calls[0][1]?.body);
      expect(vi.getTimerCount()).toBe(0);
    },
  );

  it("clears the deadline after both accepted and rejected responses", async () => {
    vi.useFakeTimers();
    respondWith(202, { data: { status: { run_id: RUN_ID } } });
    await queueReplayRun(choices);
    expect(vi.getTimerCount()).toBe(0);
    respondWith(503, { error: { code: "job_store_busy" } });
    await queueReplayRun(choices);
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("requestRunCancel", () => {
  it("posts to the run's cancel path with the ID encoded", async () => {
    const fetchMock = respondWith(200, { data: { status: { run_id: RUN_ID } } });
    expect(await requestRunCancel(RUN_ID)).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith(`/api/demo/v1/runs/${RUN_ID}/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
      signal: expect.any(AbortSignal),
    });
  });

  it("does not post an invalid run ID", async () => {
    const fetchMock = respondWith(200, {});
    expect(await requestRunCancel("../other-run")).toMatchObject({ ok: false });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    {},
    { data: { status: { run_id: "invalid" } } },
    { data: { status: { run_id: "00000000-0000-0000-0000-000000000000" } } },
  ])("does not confirm an invalid or mismatched cancellation response: %j", async (body) => {
    respondWith(200, body);
    expect(await requestRunCancel(RUN_ID)).toEqual({
      ok: false,
      message:
        "The cancellation response could not be read. Check the run status before trying again.",
    });
  });

  it.each([200, 409])("handles malformed cancellation JSON with HTTP %i", async (status) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("invalid JSON", { status })),
    );
    expect(await requestRunCancel(RUN_ID)).toMatchObject({
      ok: false,
      message: expect.stringContaining("Check the run status"),
    });
  });

  it.each([null, [], {}, { error: { code: 42 } }])(
    "handles an invalid rejection: %j",
    async (body) => {
      respondWith(409, body);
      expect(await requestRunCancel(RUN_ID)).toMatchObject({
        ok: false,
        message: expect.stringContaining("Check the run status"),
      });
    },
  );

  it("asks for a retry when the job store is busy", async () => {
    respondWith(503, { error: { code: "job_store_busy" } });
    expect(await requestRunCancel(RUN_ID)).toEqual({
      ok: false,
      message: "The job store is busy. Try cancelling again.",
    });
  });

  it("falls back to a generic failure for other rejections", async () => {
    respondWith(409, { error: { code: "already_ended" } });
    expect(await requestRunCancel(RUN_ID)).toEqual({
      ok: false,
      message: "The cancel request failed. Try again.",
    });
  });

  it("reports an unreachable service without throwing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      }),
    );
    expect(await requestRunCancel(RUN_ID)).toEqual({
      ok: false,
      message: "The local demo service could not be reached. Try again.",
    });
  });

  it.each(["headers", "success body", "error body"])(
    "bounds stalled cancellation %s and permits retry",
    async (stage) => {
      vi.useFakeTimers();
      const fetchMock = vi
        .fn<typeof fetch>()
        .mockImplementationOnce(() =>
          stage === "headers"
            ? new Promise(() => {})
            : Promise.resolve(
                new Response(new ReadableStream(), { status: stage === "error body" ? 503 : 200 }),
              ),
        )
        .mockResolvedValueOnce(Response.json({ data: { status: { run_id: RUN_ID } } }));
      vi.stubGlobal("fetch", fetchMock);
      const pending = requestRunCancel(RUN_ID);
      await vi.advanceTimersByTimeAsync(RUN_REQUEST_TIMEOUT_MS);
      expect(await pending).toEqual({
        ok: false,
        message: "The cancel request timed out. Check the run status before trying again.",
      });
      expect(fetchMock.mock.calls[0][1]?.signal?.aborted).toBe(true);
      expect(await requestRunCancel(RUN_ID)).toEqual({ ok: true });
      expect(vi.getTimerCount()).toBe(0);
    },
  );
});

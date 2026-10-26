import { afterEach, describe, expect, it, vi } from "vitest";
import { queueReplayRun, requestRunCancel } from "@/lib/runRequests";

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

afterEach(() => vi.unstubAllGlobals());

describe("queueReplayRun", () => {
  it("posts the choices to the local proxy and returns the queued run ID", async () => {
    const fetchMock = respondWith(202, { data: { status: { run_id: RUN_ID } } });
    expect(await queueReplayRun(choices)).toEqual({ ok: true, runId: RUN_ID });
    expect(fetchMock).toHaveBeenCalledWith("/api/demo/v1/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(choices),
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

  it("falls back to a generic message for an unknown error code", async () => {
    respondWith(400, { error: { code: "something_new" } });
    expect(await queueReplayRun(choices)).toMatchObject({
      ok: false,
      message: "The run request was rejected. Check the approved choices and retry.",
    });
  });

  it("treats a success without a run ID as unreadable instead of navigating nowhere", async () => {
    respondWith(202, { data: { status: {} } });
    expect(await queueReplayRun(choices)).toMatchObject({
      ok: false,
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
    expect(await queueReplayRun(choices)).toMatchObject({ ok: false, keyRejected: false });
  });
});

describe("requestRunCancel", () => {
  it("posts to the run's cancel path with the ID encoded", async () => {
    const fetchMock = respondWith(202, {});
    expect(await requestRunCancel(RUN_ID)).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith(`/api/demo/v1/runs/${RUN_ID}/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
  });

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
});

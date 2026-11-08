// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { JobDetail as Detail, JobStatus } from "@/lib/jobs/contracts";
import { RUN_REQUEST_TIMEOUT_MS } from "@/lib/runRequests";
import JobActions from "./JobActions";
import JobDetail from "./JobDetail";

const navigation = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => navigation }));

const available = <T,>(value: T) => ({
  availability: "available" as const,
  value,
  reason: null,
  detail: null,
});
const unavailable = {
  availability: "unavailable" as const,
  value: null,
  reason: "not_recorded" as const,
  detail: "Not recorded in this synthetic fixture",
};
const runId = "123e4567-e89b-12d3-a456-426614174000";

function status(state: JobStatus["state"]): JobStatus {
  return {
    record_type: "status",
    run_id: runId,
    origin: "job",
    state,
    created_at: available("2026-06-10T13:30:00Z"),
    started_at: unavailable,
    ended_at: unavailable,
    phase: available("replay"),
    progress: unavailable,
    heartbeat_at: unavailable,
    attempt: available(1),
    engine_run_id: unavailable,
    result_id: unavailable,
    cancellation: unavailable,
    failure:
      state === "failed"
        ? {
            code: "worker_lost",
            summary: "Synthetic worker stopped",
            at: "2026-06-10T14:00:00Z",
            retryable: false,
          }
        : unavailable,
  };
}

function detail(state: JobStatus["state"]): Detail {
  return {
    run: {
      record_type: "normalized_run",
      id: runId,
      strategy_id: "stock-signal",
      strategy_version: available("fixture"),
      variant: "baseline",
      dataset_id: "synthetic-fixture",
      dataset_sha256: available("a".repeat(64)),
      selected_data_sha256: available("b".repeat(64)),
      window: {
        name: "fixture-day-2",
        role: "fixture",
        start: "2026-06-10T13:30:00Z",
        end_exclusive: "2026-06-10T20:00:00Z",
      },
      observed_bounds: {},
      symbols: ["AAA"],
      feed: available("synthetic"),
      cost_policy: {
        id: "base-v2",
        spread_bps: 2,
        slippage_bps_per_fill: 1,
        fee_per_share_per_fill: 0,
        evidence: "Scenario",
      },
      accounting: {
        version: unavailable,
        mode: "recorded_costs_only",
        coverage: "incomplete",
        unresolved: ["borrow_cost"],
      },
      fill_policy: available("delayed bar"),
      session_policy: available("regular"),
      code: { revision: unavailable, source_sha256: unavailable, working_diff_sha256: unavailable },
      provenance: {
        source: "backtest",
        execution: "local_simulation",
        historical: true,
        retrospective: false,
        synthetic: true,
        evaluation: "synthetic_correctness",
        holdout_status: unavailable,
        label_evidence: [],
      },
    },
    status: status(state),
    result: null,
    artifacts: [],
  };
}

let visibility: DocumentVisibilityState;
const fetchResponse = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.useFakeTimers();
  visibility = "visible";
  vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibility);
  navigation.refresh.mockReset();
  fetchResponse.mockReset();
  vi.stubGlobal("fetch", fetchResponse);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

async function advanceTime(milliseconds: number) {
  await act(async () => vi.advanceTimersByTimeAsync(milliseconds));
}

async function changeVisibility(next: DocumentVisibilityState) {
  await act(async () => {
    visibility = next;
    document.dispatchEvent(new Event("visibilitychange"));
  });
}

it("retries failed cancellation, disables duplicate requests, and refreshes after success", async () => {
  fetchResponse.mockRejectedValueOnce(new Error("offline"));
  const view = render(<JobActions status={status("running")} />);
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Cancel run" })));
  expect(screen.getByRole("alert").textContent).toContain("could not be reached");
  let finishCancel: ((response: Response) => void) | undefined;
  fetchResponse.mockImplementationOnce(() => new Promise((resolve) => (finishCancel = resolve)));
  fireEvent.click(screen.getByRole("button", { name: "Cancel run" }));
  const cancelButton = screen.getByRole<HTMLButtonElement>("button", { name: "Cancelling…" });
  expect(cancelButton.disabled).toBe(true);
  fireEvent.click(cancelButton);
  expect(fetchResponse).toHaveBeenCalledTimes(2);
  const refreshesBeforeCancel = navigation.refresh.mock.calls.length;
  await act(async () => finishCancel?.(Response.json({ data: { status: { run_id: runId } } })));
  expect(fetchResponse).toHaveBeenLastCalledWith(
    `/api/demo/v1/runs/${runId}/cancel`,
    expect.objectContaining({ method: "POST", body: "{}" }),
  );
  expect(navigation.refresh).toHaveBeenCalledTimes(refreshesBeforeCancel + 1);
  view.rerender(<JobActions status={status("cancel_requested")} />);
  expect(screen.queryByRole("button", { name: "Cancel run" })).toBeNull();
  expect(screen.queryByRole("alert")).toBeNull();
});

it("recovers cancellation controls after a stalled body and confirms a retry", async () => {
  fetchResponse.mockResolvedValueOnce(new Response(new ReadableStream()));
  render(<JobActions status={status("running")} />);
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Cancel run" })));
  expect(screen.getByRole<HTMLButtonElement>("button", { name: "Cancelling…" }).disabled).toBe(
    true,
  );
  await advanceTime(RUN_REQUEST_TIMEOUT_MS);
  expect(screen.getByRole("alert").textContent).toContain("Check the run status");
  expect(screen.getByRole<HTMLButtonElement>("button", { name: "Cancel run" }).disabled).toBe(
    false,
  );
  expect(fetchResponse.mock.calls[0][1]?.signal?.aborted).toBe(true);

  fetchResponse.mockResolvedValueOnce(Response.json({ data: { status: { run_id: runId } } }));
  const refreshesBeforeRetry = navigation.refresh.mock.calls.length;
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Cancel run" })));
  expect(screen.queryByRole("alert")).toBeNull();
  expect(navigation.refresh).toHaveBeenCalledTimes(refreshesBeforeRetry + 1);
});

it("pauses refresh while hidden, resumes on visibility, and removes listeners on unmount", async () => {
  const removeListener = vi.spyOn(document, "removeEventListener");
  const view = render(<JobActions status={status("queued")} />);
  await advanceTime(0);
  expect(navigation.refresh).toHaveBeenCalledTimes(0);
  await advanceTime(3000);
  expect(navigation.refresh).toHaveBeenCalledTimes(1);
  await changeVisibility("hidden");
  await advanceTime(9000);
  expect(navigation.refresh).toHaveBeenCalledTimes(1);
  await changeVisibility("visible");
  expect(navigation.refresh).toHaveBeenCalledTimes(2);
  view.unmount();
  expect(removeListener).toHaveBeenCalledWith("visibilitychange", expect.any(Function));
  await changeVisibility("visible");
  await advanceTime(6000);
  expect(navigation.refresh).toHaveBeenCalledTimes(2);
  expect(vi.getTimerCount()).toBe(0);
});

it.each(["completed", "failed", "cancelled"] as const)(
  "stops refreshing after a running job becomes %s",
  async (state) => {
    const view = render(<JobDetail detail={detail("running")} warnings={[]} />);
    await advanceTime(0);
    expect(screen.getByRole("button", { name: "Cancel run" })).toBeDefined();
    view.rerender(<JobDetail detail={detail(state)} warnings={[]} />);
    expect(screen.queryByRole("button", { name: "Cancel run" })).toBeNull();
    expect(screen.queryByText("Status refreshes every 3 seconds.")).toBeNull();
    if (state === "failed")
      expect(screen.getByRole("alert").textContent).toContain(
        "worker_lost: Synthetic worker stopped",
      );
    if (state === "cancelled")
      expect(
        screen.getByText("This run was cancelled before a result was published."),
      ).toBeDefined();
    if (state === "completed")
      expect(screen.getByText(/completed legacy job has no published result record/)).toBeDefined();
    const refreshesAtCompletion = navigation.refresh.mock.calls.length;
    await advanceTime(9000);
    await changeVisibility("visible");
    expect(navigation.refresh).toHaveBeenCalledTimes(refreshesAtCompletion);
    expect(vi.getTimerCount()).toBe(0);
  },
);

it("publishes saved result metrics and artifact links when a running job completes", async () => {
  const view = render(<JobDetail detail={detail("running")} warnings={[]} />);
  await advanceTime(0);
  const completed = detail("completed");
  completed.result = {
    record_type: "result",
    id: "fixture-result",
    run_id: runId,
    window: completed.run.window,
    variant: completed.run.variant,
    provenance: completed.run.provenance,
    accounting: completed.run.accounting,
    metrics: {
      realized_net_pnl: {
        observation: available(12),
        unit: "USD",
        basis: "Saved Python result",
        source_pointer: "fixture/metrics.json",
      },
    },
    by_regime: unavailable,
    limitations: ["Synthetic correctness only"],
    artifact_ids: ["fixture-report"],
  };
  completed.artifacts = [
    {
      record_type: "artifact",
      id: "fixture-report",
      result_id: "fixture-result",
      kind: "report",
      mime_type: "text/plain",
      byte_size: 42,
      sha256: "c".repeat(64),
    },
  ];
  view.rerender(<JobDetail detail={completed} warnings={[]} />);
  expect(screen.getByText("+$12.00")).toBeDefined();
  expect(screen.getByText("USD · Saved Python result")).toBeDefined();
  expect(screen.getByText("Synthetic correctness only")).toBeDefined();
  expect(screen.getByRole<HTMLAnchorElement>("link", { name: "report" }).getAttribute("href")).toBe(
    `/api/demo/v1/runs/${runId}/artifacts/fixture-report`,
  );
  expect(screen.queryByText(/No result is published/)).toBeNull();
  expect(screen.queryByRole("button", { name: "Cancel run" })).toBeNull();
  const refreshesAtCompletion = navigation.refresh.mock.calls.length;
  await advanceTime(9000);
  expect(navigation.refresh).toHaveBeenCalledTimes(refreshesAtCompletion);
});

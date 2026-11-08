// @vitest-environment jsdom

import { Suspense, use, useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { JobStatus } from "@/lib/jobs/contracts";
import LiveStatus from "./LiveStatus";
import JobActions from "./JobActions";
import PositionsView from "./PositionsView";
import ServerDataRefresh from "./ServerDataRefresh";
import ErrorPage from "@/app/error";

const navigation = vi.hoisted(() => ({ refresh: vi.fn() }));
const operationalStatus = vi.hoisted(() =>
  vi.fn(async () => ({ latest_bar: null, runtime: [], unresolved_orders: [] })),
);
vi.mock("next/navigation", () => ({
  useRouter: () => navigation,
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/actions", () => ({ getOperationalStatus: operationalStatus }));

const unavailable = {
  availability: "unavailable" as const,
  value: null,
  reason: "not_recorded" as const,
  detail: "Not recorded in this synthetic fixture",
};
const running: JobStatus = {
  record_type: "status",
  run_id: "fixture-run",
  origin: "job",
  state: "running",
  created_at: unavailable,
  started_at: unavailable,
  ended_at: unavailable,
  phase: unavailable,
  progress: unavailable,
  heartbeat_at: unavailable,
  attempt: unavailable,
  engine_run_id: unavailable,
  result_id: unavailable,
  cancellation: unavailable,
  failure: unavailable,
};

const fetchResponse = vi.fn<typeof fetch>();
beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
  navigation.refresh.mockReset();
  operationalStatus.mockClear();
  fetchResponse.mockReset();
  fetchResponse.mockImplementation(async (url) =>
    Response.json(
      url === "/api/position-state"
        ? {
            fetched_at: new Date().toISOString(),
            stale_seconds: 30,
            accounts: [],
            pending_entries: [],
            exit_fills: [],
            closed_trades: [],
            positions: [
              {
                id: 1,
                account: "local",
                ticker: "SPY",
                backend: "local",
                provenance: "Local simulation",
                source: "live",
                signal_id: null,
                direction: "LONG",
                entry: 100,
                stop: 95,
                target: 110,
                shares: 10,
                remaining_shares: 10,
                outcome: "OPEN",
                exit_price: null,
                pnl: null,
                entry_bar: null,
                exit_bar: null,
                bars_held: null,
                created_at: new Date().toISOString(),
                closed_at: null,
                execution: null,
              },
            ],
          }
        : url === "/api/position-prices"
          ? { feed: "iex", checked_at: new Date().toISOString(), prices: {} }
          : url === "/api/operational-status"
            ? { latest_bar: null, runtime: [], unresolved_orders: [] }
            : { market_open: true, checked_at: new Date().toISOString() },
    ),
  );
  vi.stubGlobal("fetch", fetchResponse);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it.each(["overview", "positions", "active-run"])(
  "measures sixty visible seconds on %s",
  async (page) => {
    render(
      <>
        <LiveStatus />
        {page === "overview" && <ServerDataRefresh />}
        {page === "positions" && <PositionsView />}
        {page === "active-run" && <JobActions status={running} />}
      </>,
    );
    await act(async () => vi.advanceTimersByTimeAsync(0));
    for (let second = 0; second < 60; second++)
      await act(async () => vi.advanceTimersByTimeAsync(1000));
    const counts = {
      operational:
        operationalStatus.mock.calls.length +
        fetchResponse.mock.calls.filter(([url]) => url === "/api/operational-status").length,
      market: fetchResponse.mock.calls.filter(([url]) => url === "/api/market-status").length,
      state: fetchResponse.mock.calls.filter(([url]) => url === "/api/position-state").length,
      prices: fetchResponse.mock.calls.filter(([url]) => url === "/api/position-prices").length,
      route: navigation.refresh.mock.calls.length,
    };
    console.info("polling-measurement", page, counts);
    expect(counts).toEqual({
      operational: 5,
      market: 5,
      state: page === "positions" ? 13 : 0,
      prices: page === "positions" ? 13 : 0,
      route: page === "overview" ? 4 : page === "active-run" ? 20 : 0,
    });
  },
);

it("keeps last known status through a failed poll and recovers without refreshing the route", async () => {
  let statusFailed = false;
  const originalFetch = fetchResponse.getMockImplementation()!;
  fetchResponse.mockImplementation(async (url, options) => {
    if (url === "/api/operational-status") {
      if (statusFailed) throw new Error("private network details");
      return Response.json({
        latest_bar: "2026-11-07T12:00:00Z",
        runtime: [],
        unresolved_orders: [],
      });
    }
    return originalFetch(url, options);
  });
  const view = render(<LiveStatus />);
  await act(async () => vi.advanceTimersByTimeAsync(0));
  expect(view.container.textContent).toContain("2026-11-07T12:00:00Z");
  statusFailed = true;
  await act(async () => vi.advanceTimersByTimeAsync(15_000));
  expect(view.container.textContent).toContain("Displayed records may be stale");
  expect(view.container.textContent).toContain("2026-11-07T12:00:00Z");
  statusFailed = false;
  await act(async () => vi.advanceTimersByTimeAsync(15_000));
  expect(view.container.textContent).not.toContain("Displayed records may be stale");
  expect(navigation.refresh).not.toHaveBeenCalled();
});

function PendingRoute({ completion }: { completion: Promise<void> | null }) {
  if (completion) use(completion);
  return null;
}

it("does not issue another route refresh while the current transition is pending", async () => {
  let completeRefresh: () => void = () => {};
  const completion = new Promise<void>((resolve) => {
    completeRefresh = resolve;
  });
  function RefreshingPage() {
    const [pendingRoute, setPendingRoute] = useState<Promise<void> | null>(null);
    navigation.refresh.mockImplementation(() => setPendingRoute(completion));
    return (
      <Suspense fallback={<p>Loading</p>}>
        <LiveStatus />
        <ServerDataRefresh />
        <PendingRoute completion={pendingRoute} />
      </Suspense>
    );
  }
  render(<RefreshingPage />);
  for (let interval = 0; interval < 4; interval++)
    await act(async () => vi.advanceTimersByTimeAsync(15_000));
  expect(navigation.refresh).toHaveBeenCalledTimes(1);
  await act(async () => completeRefresh());
  await act(async () => vi.advanceTimersByTimeAsync(15_000));
  expect(navigation.refresh).toHaveBeenCalledTimes(2);
});

it("leaves error recovery to the retry button while layout polling continues", async () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  const retry = vi.fn();
  render(
    <>
      <LiveStatus />
      <ErrorPage error={new Error("render failed")} retry={retry} />
    </>,
  );
  for (let interval = 0; interval < 4; interval++)
    await act(async () => vi.advanceTimersByTimeAsync(15_000));
  expect(navigation.refresh).not.toHaveBeenCalled();
  expect(retry).not.toHaveBeenCalled();
  expect(log).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(retry).toHaveBeenCalledOnce();
});

it("pauses independent polls while hidden and cleans them up on unmount", async () => {
  let visibility: DocumentVisibilityState = "visible";
  vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibility);
  const view = render(
    <>
      <LiveStatus />
      <ServerDataRefresh />
    </>,
  );
  await act(async () => vi.advanceTimersByTimeAsync(0));
  expect(fetchResponse).toHaveBeenCalledTimes(2);
  await act(async () => {
    visibility = "hidden";
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(60_000);
  });
  expect(fetchResponse).toHaveBeenCalledTimes(2);
  expect(navigation.refresh).not.toHaveBeenCalled();
  await act(async () => {
    visibility = "visible";
    document.dispatchEvent(new Event("visibilitychange"));
  });
  expect(fetchResponse).toHaveBeenCalledTimes(4);
  expect(navigation.refresh).toHaveBeenCalledOnce();
  view.unmount();
  await act(async () => vi.advanceTimersByTimeAsync(60_000));
  expect(fetchResponse).toHaveBeenCalledTimes(4);
  expect(navigation.refresh).toHaveBeenCalledOnce();
  expect(vi.getTimerCount()).toBe(0);
});

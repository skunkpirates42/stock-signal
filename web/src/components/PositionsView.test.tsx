// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ExecutionAccount, ExecutionPosition, PositionState } from "@/lib/execution";
import PositionsView from "./PositionsView";

const initialTime = new Date("2026-10-29T14:00:00.000Z");

function observedAccount(account: string): ExecutionAccount {
  return {
    account,
    status: "reconciled",
    mismatch: false,
    observed_at: new Date().toISOString(),
    reconciled_at: new Date().toISOString(),
    attempted_at: new Date().toISOString(),
    observation_status: "ok",
    heartbeat_at: new Date().toISOString(),
    worker_status: "running",
    broker_positions: {},
    journal_positions: {},
  };
}

function paperPosition(id: number, account: string, ticker: string): ExecutionPosition {
  return {
    id,
    account,
    ticker,
    backend: "alpaca",
    provenance: "Alpaca paper",
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
    created_at: initialTime.toISOString(),
    closed_at: null,
    execution: null,
  };
}

function positionState(accounts = ["paper-a", "paper-b"]): PositionState {
  return {
    fetched_at: new Date().toISOString(),
    stale_seconds: 30,
    accounts: accounts.map(observedAccount),
    positions: [paperPosition(1, "paper-a", "SPY"), paperPosition(2, "paper-b", "QQQ")],
    pending_entries: [],
    exit_fills: [],
    closed_trades: [],
  };
}

const fetchResponse = vi.fn<typeof fetch>();
let visibility: DocumentVisibilityState;

async function successfulResponse(url: Parameters<typeof fetch>[0]) {
  return Response.json(
    url === "/api/position-state"
      ? positionState()
      : {
          feed: "iex",
          checked_at: new Date().toISOString(),
          prices: {
            SPY: { price: 101.25, timestamp: new Date().toISOString() },
            QQQ: { price: 102.5, timestamp: new Date().toISOString() },
          },
        },
  );
}

async function changeVisibility(next: DocumentVisibilityState) {
  await act(async () => {
    visibility = next;
    document.dispatchEvent(new Event("visibilitychange"));
  });
}

async function advanceTime(milliseconds: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(milliseconds);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(initialTime);
  visibility = "visible";
  vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibility);
  fetchResponse.mockReset();
  fetchResponse.mockImplementation(successfulResponse);
  vi.stubGlobal("fetch", fetchResponse);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it("keeps responses between clock ticks fresh and recovers from stale data and failed polls", async () => {
  let finishInitialPoll: ((response: Response) => void) | undefined;
  fetchResponse.mockImplementationOnce(
    () => new Promise((resolve) => (finishInitialPoll = resolve)),
  );
  render(<PositionsView />);
  await advanceTime(500);
  await act(async () => finishInitialPoll?.(Response.json(positionState())));
  const accountStatus = screen.getByLabelText("Paper account status");
  expect(accountStatus.textContent).toContain("reconciled");
  expect(accountStatus.textContent).not.toContain("Position data is stale");
  await advanceTime(1000);
  expect(accountStatus.textContent).not.toContain("Position data is stale");

  await changeVisibility("hidden");
  const requestsBeforeHidden = fetchResponse.mock.calls.length;
  await advanceTime(31_000);
  expect(fetchResponse).toHaveBeenCalledTimes(requestsBeforeHidden);
  fetchResponse.mockImplementation(async () =>
    Response.json({ error: "offline" }, { status: 503 }),
  );
  await changeVisibility("visible");
  expect(accountStatus.textContent).toContain("Position service unavailable");
  expect(accountStatus.textContent).toContain("current holdings and protection are unconfirmed");
  expect(screen.getByText("SPY")).toBeDefined();
  expect(screen.getByText("Last known price")).toBeDefined();
  expect(screen.getByText(/STALE PRICE/)).toBeDefined();

  fetchResponse.mockImplementation(successfulResponse);
  await advanceTime(5000);
  expect(accountStatus.textContent).toContain("reconciled");
  expect(accountStatus.textContent).not.toContain("Position service unavailable");
  expect(screen.getByText("Live price")).toBeDefined();
  expect(screen.queryByText(/STALE PRICE/)).toBeNull();
  expect(screen.queryByText(/Price service unavailable/)).toBeNull();

  await changeVisibility("hidden");
  await advanceTime(31_000);
  let finishPoll: ((response: Response) => void) | undefined;
  fetchResponse.mockImplementation((url) =>
    url === "/api/position-state"
      ? new Promise((resolve) => (finishPoll = resolve))
      : Promise.resolve(Response.json({}, { status: 503 })),
  );
  await changeVisibility("visible");
  expect(accountStatus.textContent).toContain("Position data is stale");
  await act(async () => finishPoll?.(Response.json(positionState())));
  expect(accountStatus.textContent).not.toContain("Position data is stale");
});

it("recovers from an initial failure and filters holdings when the selected account changes", async () => {
  fetchResponse.mockRejectedValueOnce(new Error("offline"));
  render(<PositionsView />);
  await advanceTime(0);
  expect(screen.getByRole("status").textContent).toContain("holdings are unknown");
  await advanceTime(5000);
  const accountStatus = screen.getByLabelText("Paper account status");
  fireEvent.click(within(accountStatus).getByText("Alpaca paper account"));
  fireEvent.change(screen.getByLabelText("Selected account"), { target: { value: "paper-b" } });
  expect(screen.getByText("QQQ")).toBeDefined();
  expect(screen.queryByText("SPY")).toBeNull();

  fetchResponse.mockImplementation(async (url) =>
    url === "/api/position-state"
      ? Response.json(positionState(["paper-a"]))
      : successfulResponse(url),
  );
  await advanceTime(5000);
  expect(screen.getByLabelText<HTMLSelectElement>("Selected account").value).toBe("paper-a");
  expect(screen.getByText("SPY")).toBeDefined();
  expect(screen.queryByText("QQQ")).toBeNull();
});

it("keeps reconciliation evidence, protection warnings and actual fills scoped through account changes", async () => {
  const state = positionState();
  state.stale_seconds = 60;
  state.accounts[0] = {
    ...state.accounts[0],
    mismatch: true,
    broker_positions: null,
    journal_positions: { SPY: 10 },
  };
  const execution: NonNullable<ExecutionPosition["execution"]> = {
    entry: null,
    protection: "confirmed",
    pending_exit: null,
    legs: {
      stop: {
        state: "accepted",
        coverage: true,
        current: true,
        quantity: 10,
        updated_at: initialTime.toISOString(),
      },
    },
  };
  state.positions = state.positions.map((position) => ({ ...position, execution }));
  const pendingEntries = ["paper-a", "paper-b"].map((account, index) => ({
    id: `pending-${account}`,
    account,
    ticker: index === 0 ? "MSFT" : "AMZN",
    state: "partially_filled",
    requested_qty: 10,
    filled_qty: 2,
    fill_price: null,
    updated_at: initialTime.toISOString(),
    purpose: "entry",
    pending_exit: "cancel_requested",
    stop: 95,
    target: 110,
    execution: {
      ...execution,
      legs: {
        stop: {
          ...execution.legs.stop,
          state: "held",
          updated_at: new Date(initialTime.getTime() - 31_000).toISOString(),
        },
      },
    },
  }));
  state.pending_entries = pendingEntries;
  state.exit_fills = pendingEntries.map((entry) => ({
    ...entry,
    id: `exit-${entry.account}`,
    purpose: "exit",
    reason: null,
    fill_price: entry.account === "paper-a" ? null : 101.25,
  }));
  state.closed_trades = state.positions.map((position, index) => ({
    ...position,
    id: 10 + index,
    ticker: index === 0 ? "IWM" : "DIA",
    outcome: "WIN",
    exit_price: 110,
    pnl: 100,
  }));
  fetchResponse.mockImplementation(async (url) =>
    url === "/api/position-state" ? Response.json(state) : successfulResponse(url),
  );
  render(<PositionsView />);
  await advanceTime(0);
  const accountStatus = screen.getByLabelText("Paper account status");
  fireEvent.click(within(accountStatus).getByText("Alpaca paper account"));
  expect(accountStatus.textContent).toContain('Broker: null; journal: {"SPY":10}');
  expect(accountStatus.textContent).toContain("current protection is not confirmed");
  expect(accountStatus.textContent).toContain("MSFT · pending Alpaca paper entry");
  expect(accountStatus.textContent).not.toContain("AMZN");
  const exitFills = screen.getByLabelText("Actual broker exit fills");
  expect(exitFills.textContent).toContain("MSFT · exit · partially_filled · 2 shares at —");
  expect(screen.getByText("IWM")).toBeDefined();
  expect(screen.queryByText("DIA")).toBeNull();

  fireEvent.change(screen.getByLabelText("Selected account"), { target: { value: "paper-b" } });
  expect(accountStatus.textContent).not.toContain("Journal/broker mismatch");
  expect(accountStatus.textContent).toContain("Protection confirmed at last observation");
  expect(accountStatus.textContent).toContain("AMZN · pending Alpaca paper entry");
  expect(accountStatus.textContent).not.toContain("MSFT");
  expect(accountStatus.textContent).toContain("actual average — · protection awaiting entry fill");
  expect(accountStatus.textContent).toContain(
    "held · awaiting activation · not confirmed active · observation stale/unknown",
  );
  expect(exitFills.textContent).toContain("AMZN · exit · partially_filled · 2 shares at $101.25");
  expect(exitFills.textContent).not.toContain("MSFT");
  expect(screen.getByText("DIA")).toBeDefined();
  expect(screen.queryByText("IWM")).toBeNull();
});

it("aborts in-flight requests and removes polling and clock listeners on unmount", async () => {
  const removeListener = vi.spyOn(document, "removeEventListener");
  let requestSignal: AbortSignal | undefined;
  let finishPoll: ((response: Response) => void) | undefined;
  fetchResponse.mockImplementation((_url, options) => {
    requestSignal = options?.signal ?? undefined;
    return new Promise((resolve) => (finishPoll = resolve));
  });
  const view = render(<PositionsView />);
  expect(requestSignal?.aborted).toBe(false);
  view.unmount();
  expect(requestSignal?.aborted).toBe(true);
  expect(removeListener.mock.calls.filter(([name]) => name === "visibilitychange")).toHaveLength(2);
  await act(async () => finishPoll?.(Response.json(positionState())));
  await changeVisibility("visible");
  await advanceTime(60_000);
  expect(fetchResponse).toHaveBeenCalledTimes(1);
  expect(vi.getTimerCount()).toBe(0);
});

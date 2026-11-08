import { describe, expect, it } from "vitest";
import { deriveAccountPositionView } from "./accountPositionView";
import type {
  ExecutionAccount,
  ExecutionOrder,
  ExecutionPosition,
  PositionState,
} from "./execution";

const now = new Date("2026-10-29T14:00:30Z");
const observedAt = "2026-10-29T14:00:00Z";

function observedAccount(account: string): ExecutionAccount {
  return {
    account,
    status: "reconciled",
    mismatch: false,
    observed_at: observedAt,
    reconciled_at: observedAt,
    attempted_at: observedAt,
    observation_status: "ok",
    heartbeat_at: observedAt,
    worker_status: "running",
    broker_positions: { SPY: 10 },
    journal_positions: { SPY: 10 },
  };
}

function order(id: string, account: string): ExecutionOrder & { account: string } {
  return {
    id,
    account,
    state: "partially_filled",
    requested_qty: 10,
    filled_qty: 2,
    fill_price: 101.25,
    updated_at: observedAt,
    ticker: "SPY",
    purpose: "entry",
  };
}

function position(id: number, account: string): ExecutionPosition {
  return {
    id,
    account,
    ticker: "SPY",
    source: "live",
    backend: "alpaca",
    provenance: "Alpaca paper",
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
    created_at: observedAt,
    closed_at: null,
    execution: {
      entry: order(`entry-${id}`, account),
      protection: "confirmed",
      pending_exit: null,
      legs: {},
    },
  };
}

function positionState(): PositionState {
  const positions: ExecutionPosition[] = [
    position(1, "paper-a"),
    position(2, "paper-b"),
    {
      ...position(3, "local-a"),
      backend: "local",
      provenance: "Local simulation",
      execution: null,
    },
    { ...position(4, "paper-b"), source: "backtest", provenance: "Replay", execution: null },
    {
      ...position(5, ""),
      account: null,
      backend: null,
      provenance: "Unknown provenance",
      execution: null,
    },
    { ...position(6, ""), account: null, provenance: "Alpaca paper" },
  ];
  return {
    fetched_at: observedAt,
    stale_seconds: 30,
    accounts: [observedAccount("paper-a"), observedAccount("paper-b")],
    positions,
    pending_entries: ["paper-a", "paper-b"].map((account) => ({
      ...order(`pending-${account}`, account),
      pending_exit: "cancel_requested",
      stop: 95,
      target: 110,
      execution: null,
    })),
    exit_fills: ["paper-a", "paper-b"].map((account) => ({
      ...order(`exit-${account}`, account),
      purpose: "exit",
      reason: null,
    })),
    closed_trades: positions.map((trade) => ({
      ...trade,
      outcome: "WIN",
      exit_price: 110,
      pnl: 100,
    })),
  };
}

function derive(positionState: PositionState, requestedAccount = "", pollFailed = false) {
  return deriveAccountPositionView({ positionState, requestedAccount, pollFailed, now });
}

describe("account-position view", () => {
  it("scopes paper holdings, pending entries, broker exit fills and closed trades to the chosen account", () => {
    const state = positionState();
    const before = structuredClone(state);
    const view = derive(state, "paper-b");
    expect(view.selectedAccount).toBe("paper-b");
    expect(view.accountObservation).toBe(state.accounts[1]);
    expect(view.positions.map((position) => position.id)).toEqual([2, 3, 4, 5]);
    expect(view.executionPositions.map((position) => position.id)).toEqual([2]);
    expect(view.pendingEntries.map((entry) => entry.id)).toEqual(["pending-paper-b"]);
    expect(view.exitFills.map((fill) => fill.id)).toEqual(["exit-paper-b"]);
    // Closed trades retain the existing backend-based scope, including replay rows.
    expect(view.closedTrades.map((trade) => trade.id)).toEqual([2, 3, 4, 5]);
    expect(view.positions[3].account).toBeNull();
    expect(view.positions[3].provenance).toBe("Unknown provenance");
    expect(view.pendingEntries[0].fill_price).toBe(101.25);
    expect(state).toEqual(before);
  });

  it("uses the first observed account until a valid account is requested", () => {
    const state = positionState();
    expect(derive(state).selectedAccount).toBe("paper-a");
    expect(derive(state, "unobserved").selectedAccount).toBe("paper-a");
    expect(derive(state, "paper-b").selectedAccount).toBe("paper-b");
    state.accounts.reverse();
    expect(derive(state, "paper-a").selectedAccount).toBe("paper-a");
    expect(derive(state).selectedAccount).toBe("paper-b");
  });

  it("falls back when an account disappears and preserves the requested account if it reappears", () => {
    const state = positionState();
    const requestedAccount = "paper-b";
    const selected = derive(state, requestedAccount);
    const removed = derive({ ...state, accounts: [state.accounts[0]] }, requestedAccount);
    const restored = derive(state, requestedAccount);
    expect(selected.positions.map((position) => position.id)).toContain(2);
    expect(removed.selectedAccount).toBe("paper-a");
    expect(removed.positions.map((position) => position.id)).not.toContain(2);
    expect(removed.pendingEntries[0].account).toBe("paper-a");
    expect(removed.exitFills[0].account).toBe("paper-a");
    expect(restored.selectedAccount).toBe(requestedAccount);
  });

  it("keeps missing account observations unknown without adopting unscoped paper records", () => {
    const view = derive({ ...positionState(), accounts: [] }, "paper-b");
    expect(view.selectedAccount).toBeUndefined();
    expect(view.accountObservation).toBeUndefined();
    expect(view.statusLabel).toBe("No account observed");
    expect(view.isBrokerObservationCurrent).toBe(false);
    expect(view.isExecutionCurrent).toBe(false);
    expect(view.workerStatus).toBe("stale / unknown");
    expect(view.positions.map((position) => position.id)).toEqual([3, 4, 5]);
    expect(view.closedTrades.map((trade) => trade.id)).toEqual([3, 5]);
    expect(view.pendingEntries).toEqual([]);
    expect(view.exitFills).toEqual([]);
  });

  it("accepts observations at the freshness limit and respects the endpoint's declared limit", () => {
    const state = positionState();
    const view = derive(state);
    expect(view.isPositionStateCurrent).toBe(true);
    expect(view.isBrokerObservationCurrent).toBe(true);
    expect(view.isExecutionCurrent).toBe(true);
    expect(view.statusLabel).toBe("reconciled");
    expect(view.protectionWarning).toBeNull();
    expect(derive({ ...state, stale_seconds: 29 }).isPositionStateCurrent).toBe(false);
    expect(derive({ ...state, stale_seconds: 60 }).isBrokerObservationCurrent).toBe(true);
  });

  it.each([null, "bad", "2026-10-29T13:59:59Z", "2026-10-29T14:00:31Z"])(
    "keeps stale, missing, invalid and future broker observations unconfirmed: %s",
    (observed_at) => {
      const state = positionState();
      state.accounts[0].observed_at = observed_at;
      const view = derive(state);
      expect(view.isPositionStateCurrent).toBe(true);
      expect(view.isBrokerObservationCurrent).toBe(false);
      expect(view.isExecutionCurrent).toBe(false);
      expect(view.statusLabel).toBe("Broker observation stale / unavailable");
      expect(view.workerStatus).toBe("running");
    },
  );

  it.each(["bad", "2026-10-29T13:59:59Z", "2026-10-29T14:00:31Z"])(
    "invalidates broker freshness when the endpoint observation is not current: %s",
    (fetched_at) => {
      const state = positionState();
      const view = derive({ ...state, fetched_at });
      expect(view.statusLabel).toBe("Position data is stale");
      expect(view.statusNeedsAttention).toBe(true);
      expect(view.isBrokerObservationCurrent).toBe(false);
      expect(view.isExecutionCurrent).toBe(false);
      expect(view.protectionWarning).toBe("Current protection is unconfirmed.");
      expect(view.positions).toHaveLength(4);
    },
  );

  it("retains last-known records on a failed poll without confirming current protection", () => {
    const state = positionState();
    const view = derive(state, "paper-b", true);
    expect(view.statusLabel).toBe("Position service unavailable");
    expect(view.isPositionStateCurrent).toBe(false);
    expect(view.isBrokerObservationCurrent).toBe(false);
    expect(view.isExecutionCurrent).toBe(false);
    expect(view.protectionWarning).toContain("current holdings and protection are unconfirmed");
    expect(view.pendingEntries[0]).toBe(state.pending_entries[1]);
    expect(view.exitFills[0]).toBe(state.exit_fills[1]);
    expect(view.workerStatus).toBe("running");
  });

  it("marks reconciliation mismatches for attention without repairing or hiding broker evidence", () => {
    const state = positionState();
    state.accounts[0] = { ...state.accounts[0], mismatch: true, broker_positions: null };
    const before = structuredClone(state);
    const view = derive(state);
    expect(view.statusNeedsAttention).toBe(true);
    expect(view.isBrokerObservationCurrent).toBe(true);
    expect(view.isExecutionCurrent).toBe(false);
    expect(view.accountObservation?.broker_positions).toBeNull();
    expect(view.accountObservation?.journal_positions).toEqual({ SPY: 10 });
    expect(view.positions.map((position) => position.id)).toContain(1);
    expect(state).toEqual(before);
    expect(derive(state, "paper-b").isExecutionCurrent).toBe(true);
    expect(derive(state, "paper-b").statusNeedsAttention).toBe(false);
  });

  it.each([null, "bad", "2026-10-29T13:59:59Z", "2026-10-29T14:00:31Z"])(
    "expires worker status independently of current broker observations: %s",
    (heartbeat_at) => {
      const state = positionState();
      state.accounts[0].heartbeat_at = heartbeat_at;
      const view = derive(state);
      expect(view.isBrokerObservationCurrent).toBe(true);
      expect(view.isExecutionCurrent).toBe(true);
      expect(view.workerStatus).toBe("stale / unknown");
    },
  );
});

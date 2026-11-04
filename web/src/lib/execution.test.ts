import { expect, it } from "vitest";
import { observationFresh, provenance, readPositionState } from "./execution";
import type { Trade } from "./types";
it("expires observations independently of fetches or prices", () => {
  const now = new Date("2026-10-29T14:00:31Z");
  expect(observationFresh("2026-10-29T14:00:00Z", now)).toBe(false);
  expect(observationFresh("2026-10-29T14:00:01Z", now)).toBe(true);
  expect(observationFresh(null, now)).toBe(false);
  expect(observationFresh("bad", now)).toBe(false);
  expect(observationFresh("2026-10-29T14:01:00Z", now)).toBe(false);
});
it("does not infer broker ownership from live source", () => {
  const trade = { source: "live" } as Trade;
  expect(provenance(trade)).toBe("Unknown provenance");
  expect(provenance({ ...trade, backend: "local", account: "a" })).toBe("Local simulation");
  expect(provenance({ ...trade, backend: "alpaca", account: "a" })).toBe("Alpaca paper");
  expect(provenance({ ...trade, backend: "alpaca", account: "a", source: "backtest" })).toBe(
    "Replay",
  );
});

const order = {
  id: "ord-1",
  state: "accepted",
  requested_qty: 10,
  filled_qty: 0,
  fill_price: null,
  updated_at: "2026-10-29T14:00:00Z",
  ticker: "SPY",
  purpose: "entry",
};
const positionState = {
  fetched_at: "2026-10-29T14:00:01Z",
  stale_seconds: 30,
  accounts: [
    {
      account: "PA1",
      status: "observed",
      mismatch: false,
      observed_at: "2026-10-29T14:00:00Z",
      reconciled_at: null,
      attempted_at: null,
      observation_status: "ok",
      heartbeat_at: null,
      worker_status: "unknown",
      broker_positions: null,
      journal_positions: { SPY: 10 },
    },
  ],
  positions: [],
  pending_entries: [
    {
      ...order,
      account: "PA1",
      pending_exit: null,
      stop: 95,
      target: null,
      execution: {
        entry: order,
        protection: "unconfirmed",
        pending_exit: null,
        legs: {
          stop: { state: "missing", coverage: false, current: false, quantity: null },
          target: {
            ...order,
            purpose: "exit",
            state: "held",
            coverage: true,
            current: true,
            quantity: 10,
          },
        },
      },
    },
  ],
  exit_fills: [],
  closed_trades: [],
};

it("parses pending entries with their bracket legs", () => {
  const parsed = readPositionState(positionState, "position-state");
  const legs = parsed.pending_entries[0].execution!.legs;
  expect(legs.stop).toEqual({
    state: "missing",
    coverage: false,
    current: false,
    quantity: null,
    updated_at: undefined,
  });
  expect(legs.target.updated_at).toBe("2026-10-29T14:00:00Z");
  expect(parsed.accounts[0].journal_positions).toEqual({ SPY: 10 });
});

it("rejects position state whose broker quantities are not numbers", () => {
  const account = { ...positionState.accounts[0], broker_positions: { SPY: "10" } };
  expect(() =>
    readPositionState({ ...positionState, accounts: [account] }, "position-state"),
  ).toThrow("position-state.accounts[0].broker_positions.SPY: expected finite number");
  expect(() => readPositionState({ ...positionState, positions: null }, "position-state")).toThrow(
    "position-state.positions: expected array",
  );
});

import {
  readArrayOf,
  readBoolean,
  readFields,
  readNullable,
  readNumber,
  readOptional,
  readRecordOf,
  readString,
  type Read,
} from "./parse";
import { readTrade, type Trade } from "./types";

export interface ExecutionOrder {
  id: string;
  state: string;
  requested_qty: number;
  filled_qty: number;
  fill_price: number | null;
  updated_at: string;
  ticker: string;
  purpose: string;
}
export interface ExecutionPosition extends Trade {
  provenance: string;
  execution: null | {
    entry: ExecutionOrder | null;
    protection: string;
    pending_exit: string | null;
    legs: Record<
      string,
      Partial<ExecutionOrder> & {
        state: string;
        coverage: boolean;
        current: boolean;
        quantity: number | null;
      }
    >;
  };
}
export interface ExecutionAccount {
  account: string;
  status: string;
  mismatch: boolean;
  observed_at: string | null;
  reconciled_at: string | null;
  attempted_at: string | null;
  observation_status: string;
  heartbeat_at: string | null;
  worker_status: string;
  broker_positions: Record<string, number> | null;
  journal_positions: Record<string, number>;
}
export interface PositionState {
  fetched_at: string;
  stale_seconds: number;
  accounts: ExecutionAccount[];
  positions: ExecutionPosition[];
  pending_entries: (ExecutionOrder & {
    account: string;
    pending_exit: string | null;
    stop: number | null;
    target: number | null;
    execution: ExecutionPosition["execution"];
  })[];
  exit_fills: (ExecutionOrder & { account: string; reason: string | null })[];
  closed_trades: Trade[];
}
export function observationFresh(timestamp: string | null, now: Date, seconds = 30) {
  if (!timestamp) return false;
  const age = now.getTime() - Date.parse(timestamp);
  return age >= 0 && age <= seconds * 1000;
}
export function provenance(trade: Trade) {
  if (trade.source === "backtest" || trade.source === "poc") return "Replay";
  if (trade.source === "live" && trade.account) {
    if (trade.backend === "alpaca") return "Alpaca paper";
    if (trade.backend === "local") return "Local simulation";
  }
  return "Unknown provenance";
}

const readNullableNumber = readNullable(readNumber);
const readNullableString = readNullable(readString);

const readExecutionOrder: Read<ExecutionOrder> = (value, path) => {
  const field = readFields(value, path);
  return {
    id: field("id", readString),
    state: field("state", readString),
    requested_qty: field("requested_qty", readNumber),
    filled_qty: field("filled_qty", readNumber),
    fill_price: field("fill_price", readNullableNumber),
    updated_at: field("updated_at", readString),
    ticker: field("ticker", readString),
    purpose: field("purpose", readString),
  };
};

type ExecutionLeg = NonNullable<ExecutionPosition["execution"]>["legs"][string];

const readExecutionLeg: Read<ExecutionLeg> = (value, path) => {
  const field = readFields(value, path);
  return {
    state: field("state", readString),
    coverage: field("coverage", readBoolean),
    current: field("current", readBoolean),
    quantity: field("quantity", readNullableNumber),
    updated_at: field("updated_at", readOptional(readNullableString)) ?? undefined,
  };
};

const readExecution: Read<ExecutionPosition["execution"]> = readNullable((value, path) => {
  const field = readFields(value, path);
  return {
    entry: field("entry", readNullable(readExecutionOrder)),
    protection: field("protection", readString),
    pending_exit: field("pending_exit", readNullableString),
    legs: field("legs", readRecordOf(readExecutionLeg)),
  };
});

const readExecutionPosition: Read<ExecutionPosition> = (value, path) => {
  const field = readFields(value, path);
  return {
    ...readTrade(value, path),
    provenance: field("provenance", readString),
    execution: field("execution", readExecution),
  };
};

const readPositionCounts = readRecordOf(readNumber);

const readExecutionAccount: Read<ExecutionAccount> = (value, path) => {
  const field = readFields(value, path);
  return {
    account: field("account", readString),
    status: field("status", readString),
    mismatch: field("mismatch", readBoolean),
    observed_at: field("observed_at", readNullableString),
    reconciled_at: field("reconciled_at", readNullableString),
    attempted_at: field("attempted_at", readNullableString),
    observation_status: field("observation_status", readString),
    heartbeat_at: field("heartbeat_at", readNullableString),
    worker_status: field("worker_status", readString),
    broker_positions: field("broker_positions", readNullable(readPositionCounts)),
    journal_positions: field("journal_positions", readPositionCounts),
  };
};

const readPendingEntry: Read<PositionState["pending_entries"][number]> = (value, path) => {
  const field = readFields(value, path);
  return {
    ...readExecutionOrder(value, path),
    account: field("account", readString),
    pending_exit: field("pending_exit", readNullableString),
    stop: field("stop", readNullableNumber),
    target: field("target", readNullableNumber),
    execution: field("execution", readExecution),
  };
};

const readExitFill: Read<PositionState["exit_fills"][number]> = (value, path) => {
  const field = readFields(value, path);
  return {
    ...readExecutionOrder(value, path),
    account: field("account", readString),
    reason: field("reason", readNullableString),
  };
};

export const readPositionState: Read<PositionState> = (value, path) => {
  const field = readFields(value, path);
  return {
    fetched_at: field("fetched_at", readString),
    stale_seconds: field("stale_seconds", readNumber),
    accounts: field("accounts", readArrayOf(readExecutionAccount)),
    positions: field("positions", readArrayOf(readExecutionPosition)),
    pending_entries: field("pending_entries", readArrayOf(readPendingEntry)),
    exit_fills: field("exit_fills", readArrayOf(readExitFill)),
    closed_trades: field("closed_trades", readArrayOf(readTrade)),
  };
};

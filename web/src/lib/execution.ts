import type { Trade } from "./types";

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

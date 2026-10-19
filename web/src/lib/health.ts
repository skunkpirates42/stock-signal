export function heartbeatState(timestamp: string, now: number): "fresh" | "stale" {
  const age = now - Date.parse(timestamp);
  return Number.isFinite(age) && age >= -5000 && age <= 30000 ? "fresh" : "stale";
}

export type ApiState = "checking" | "ok" | "unavailable";
export type HeartbeatSummary = "fresh" | "stale" | "none" | "unknown";

export interface RuntimeRow { scope: string; status: string; updated_at: string; detail: string; data_at: string | null }
export interface UnresolvedOrder { id: string; ticker: string; purpose: string; state: string; filled_qty: number; requested_qty: number }
export interface OperationalStatus { latest_bar: string | null; runtime: RuntimeRow[]; unresolved_orders: UnresolvedOrder[] }

export interface StatusSummary {
  scope: "Live" | "All sources";
  api: ApiState;
  heartbeat: HeartbeatSummary;
  checkedAt: string | null;
  latestBar: string | null;
  runtime: (RuntimeRow & { heartbeat: "fresh" | "stale" })[];
  unresolvedOrders: UnresolvedOrder[];
}

export function describeStatus({ source, status, apiFailed, checkedAt }: {
  source: string | null;
  status: OperationalStatus | null;
  apiFailed: boolean;
  checkedAt: string | null;
}): StatusSummary {
  const api: ApiState = apiFailed ? "unavailable" : status ? "ok" : "checking";
  const runtime = (status?.runtime ?? []).map(row => ({
    ...row,
    heartbeat: heartbeatState(row.updated_at, Date.parse(checkedAt ?? row.updated_at)),
  }));
  let heartbeat: HeartbeatSummary;
  if (api !== "ok") heartbeat = "unknown";
  else if (runtime.length === 0) heartbeat = "none";
  else heartbeat = runtime.some(row => row.heartbeat === "stale") ? "stale" : "fresh";
  return {
    scope: source === "all" ? "All sources" : "Live",
    api,
    heartbeat,
    checkedAt,
    latestBar: status?.latest_bar ?? null,
    runtime,
    unresolvedOrders: status?.unresolved_orders ?? [],
  };
}

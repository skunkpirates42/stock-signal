"use server";

import { API_BASE } from "@/lib/api";
import type { ExplainResult } from "@/lib/types";

export async function explainSignal(signalId: number): Promise<ExplainResult> {
  const response = await fetch(`${API_BASE}/api/signals/${signalId}/explain`, {
    method: "POST",
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`explain responded ${response.status}`);
  }
  return response.json() as Promise<ExplainResult>;
}

export async function getOperationalStatus() {
  const response = await fetch(`${API_BASE}/api/status`, { cache: "no-store", signal: AbortSignal.timeout(10000) });
  if (!response.ok) throw new Error(`Status responded ${response.status}`);
  return response.json() as Promise<{
    latest_bar: string | null;
    runtime: { scope: string; status: string; updated_at: string; detail: string; data_at: string | null }[];
    unresolved_orders: { id: string; ticker: string; purpose: string; state: string; filled_qty: number; requested_qty: number }[];
  }>;
}

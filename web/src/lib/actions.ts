"use server";

import { API_BASE } from "@/lib/api";
import { readOperationalStatus, type OperationalStatus } from "@/lib/health";
import { readExplainResult, type ExplainResult } from "@/lib/types";

export async function explainSignal(signalId: number): Promise<ExplainResult> {
  const response = await fetch(`${API_BASE}/api/signals/${signalId}/explain`, {
    method: "POST",
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`explain responded ${response.status}`);
  }
  return readExplainResult(await response.json(), "explain");
}

export async function getOperationalStatus(): Promise<OperationalStatus> {
  const response = await fetch(`${API_BASE}/api/status`, {
    cache: "no-store",
    signal: AbortSignal.timeout(10000),
  });
  if (!response.ok) throw new Error(`Status responded ${response.status}`);
  return readOperationalStatus(await response.json(), "status");
}

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

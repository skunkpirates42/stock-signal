import { API_BASE } from "@/lib/api";

export type AvailabilityReason =
  | "not_recorded"
  | "not_modeled"
  | "not_applicable"
  | "missing_artifact"
  | "unverified"
  | "unknown_legacy"
  | "not_registered";

export interface Available<T> {
  availability: "available";
  value: T;
  reason: null;
  detail: string | null;
}

export interface Unavailable {
  availability: "unavailable";
  value: null;
  reason: AvailabilityReason;
  detail: string;
}

export type Availability<T> = Available<T> | Unavailable;

export interface Provenance {
  source: "backtest" | "live" | "unknown";
  execution: "local_simulation" | "paper" | "unknown";
  historical: boolean;
  retrospective: boolean;
  synthetic: boolean;
  evaluation: "retrospective" | "synthetic_correctness" | "prospective" | "unknown";
  holdout_status: Availability<"upcoming" | "collecting" | "complete" | "reviewable">;
  label_evidence: string[];
}

export interface Window {
  name: string;
  role: "development" | "holdout" | "evaluation" | "fixture" | "unknown";
  start: string;
  end_exclusive: string;
}

export interface Accounting {
  version: Availability<string>;
  mode: "recorded_costs_only" | "cashflow_accounted" | "unknown";
  coverage: "complete" | "incomplete" | "unavailable";
  unresolved: string[];
}

export interface Metric {
  observation: Availability<number>;
  unit: string;
  basis: string;
  source_pointer: string | null;
}

export interface Result {
  record_type: "result";
  id: string;
  run_id: string;
  window: Window;
  variant: string;
  provenance: Provenance;
  accounting: Accounting;
  metrics: Record<string, Metric>;
  by_regime: Availability<{
    basis: string;
    unit: "USD";
    source_pointer: string;
    values: Record<string, { n: number; wins: number; win_rate: number; pnl: number }>;
  }>;
  limitations: string[];
  artifact_ids: string[];
}

export interface NormalizedRun {
  record_type: "normalized_run";
  id: string;
  strategy_id: "stock-signal";
  strategy_version: Availability<string>;
  variant: string;
  dataset_id: string;
  dataset_sha256: Availability<string>;
  selected_data_sha256: Availability<string>;
  window: Window;
  observed_bounds: Record<string, Availability<string>>;
  symbols: string[];
  feed: Availability<string>;
  cost_policy: {
    id: string;
    spread_bps: number;
    slippage_bps_per_fill: number;
    fee_per_share_per_fill: number;
    evidence: string;
  };
  accounting: Accounting;
  fill_policy: Availability<string>;
  session_policy: Availability<string>;
  code: Record<string, Availability<string>>;
  provenance: Provenance;
}

export interface Artifact {
  record_type: "artifact";
  id: string;
  result_id: string;
  kind: string;
  sha256: string;
  mime_type: string;
  byte_size: number;
}

export interface SavedResultDetail {
  result: Result;
  run: NormalizedRun;
  artifacts: Artifact[];
  status: { origin: "saved_artifact" | "job"; state: string; run_id: string };
}

export interface SavedDiagnostics {
  signal_execution_reasons: Record<string, number>;
  candidate_gate_checks: Record<string, number>;
}

interface Envelope<T> {
  schema_version: 1;
  data: T;
  warnings: string[];
}

export class DemoNotFound extends Error {
  override name = "DemoNotFound";
}

const OPAQUE_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export function isOpaqueDemoId(value: string): boolean {
  return OPAQUE_ID.test(value);
}

async function demoGet<T>(path: string): Promise<Envelope<T>> {
  const response = await fetch(`${API_BASE}/api/demo/v1${path}`, { cache: "no-store" });
  if (response.status === 404) throw new DemoNotFound("Saved demo record was not found");
  if (!response.ok) throw new Error(`${path} responded ${response.status}`);
  return response.json() as Promise<Envelope<T>>;
}

export async function getResearchResults(cursor?: string) {
  if (cursor !== undefined && !isOpaqueDemoId(cursor)) throw new DemoNotFound("Saved demo cursor was not found");
  const params = new URLSearchParams({ limit: "50" });
  if (cursor) params.set("cursor", cursor);
  return demoGet<{ results: Result[]; next_cursor: string | null }>(`/research?${params}`);
}

/**
 * A3 has a result-detail endpoint only. The /runs/[runId] UI route uses its opaque
 * segment as that result ID and renders the saved normalized run ID separately.
 */
export async function getSavedResult(resultId: string) {
  if (!isOpaqueDemoId(resultId)) throw new DemoNotFound("Saved demo result was not found");
  return demoGet<SavedResultDetail>(`/results/${encodeURIComponent(resultId)}`);
}

const MAX_ARTIFACT_BYTES = 1024 * 1024;

function countMap(value: unknown): Record<string, number> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const entries = Object.entries(value);
  if (!entries.every(([key, count]) => key.length > 0 && typeof count === "number"
    && Number.isSafeInteger(count) && count >= 0)) return null;
  return Object.fromEntries(entries);
}

async function readBoundedBody(response: Response, expectedBytes: number): Promise<Uint8Array | null> {
  if (!response.body) return null;
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > MAX_ARTIFACT_BYTES || total > expectedBytes) {
        await reader.cancel();
        return null;
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  if (total !== expectedBytes) return null;
  const body = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body;
}

/** Read only the two aggregate count maps supported by the saved diagnostics schema. */
export async function getSavedDiagnostics(
  resultId: string,
  artifacts: Artifact[],
): Promise<Availability<SavedDiagnostics>> {
  const artifact = artifacts.find((item) => item.kind === "diagnostics");
  if (!artifact) {
    return { availability: "unavailable", value: null, reason: "missing_artifact", detail: "No indexed diagnostics artifact is available for this result." };
  }
  if (!isOpaqueDemoId(resultId) || !isOpaqueDemoId(artifact.id) || artifact.result_id !== resultId) {
    return { availability: "unavailable", value: null, reason: "unverified", detail: "The indexed diagnostics reference is not valid for this result." };
  }

  try {
    const response = await fetch(
      `${API_BASE}/api/demo/v1/results/${encodeURIComponent(resultId)}/artifacts/${encodeURIComponent(artifact.id)}`,
      { cache: "no-store", redirect: "manual" },
    );
    const contentType = response.headers.get("content-type")?.split(";", 1)[0].trim();
    const contentLength = response.headers.get("content-length");
    const declaredLength = contentLength === null ? Number.NaN : Number(contentLength);
    if (!response.ok || contentType !== "application/json" || !Number.isSafeInteger(declaredLength)
      || declaredLength < 0 || declaredLength > MAX_ARTIFACT_BYTES) {
      return { availability: "unavailable", value: null, reason: "unverified", detail: "The saved diagnostics could not be verified as bounded JSON." };
    }
    const body = await readBoundedBody(response, declaredLength);
    if (!body) throw new Error("Diagnostics length mismatch");
    const raw: unknown = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(body));
    if (typeof raw !== "object" || raw === null || Array.isArray(raw)) throw new Error("Invalid diagnostics object");
    const record = raw as Record<string, unknown>;
    const signalReasons = countMap(record.signal_execution_reasons);
    const gateChecks = countMap(record.candidate_gate_checks);
    if (!signalReasons || !gateChecks) throw new Error("Unsupported diagnostics schema");
    return {
      availability: "available",
      value: { signal_execution_reasons: signalReasons, candidate_gate_checks: gateChecks },
      reason: null,
      detail: "Saved aggregate counts from the indexed diagnostics artifact.",
    };
  } catch {
    return { availability: "unavailable", value: null, reason: "unverified", detail: "The indexed diagnostics artifact does not contain the supported saved aggregate counts." };
  }
}

export function artifactHref(resultId: string, artifactId: string) {
  return `/api/demo/v1/results/${encodeURIComponent(resultId)}/artifacts/${encodeURIComponent(artifactId)}`;
}

export function availabilityText(value: Availability<string>): string {
  return value.availability === "available" ? value.value : `Unavailable: ${value.detail}`;
}

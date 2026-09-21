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

export function artifactHref(resultId: string, artifactId: string) {
  return `/api/demo/v1/results/${encodeURIComponent(resultId)}/artifacts/${encodeURIComponent(artifactId)}`;
}

export function availabilityText(value: Availability<string>): string {
  return value.availability === "available" ? value.value : `Unavailable: ${value.detail}`;
}

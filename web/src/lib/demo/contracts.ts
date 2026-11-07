import {
  readArrayOf,
  readFields,
  readLiteral,
  readNullable,
  readString,
  type Read,
} from "@/lib/parse";

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

export interface Envelope<T> {
  schema_version: 1;
  data: T;
  warnings: string[];
}

const OPAQUE_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export function isOpaqueDemoId(value: string): boolean {
  return OPAQUE_ID.test(value);
}

export function readEnvelope<T>(readData: Read<T>): Read<Envelope<T>> {
  return (value, path) => {
    const field = readFields(value, path);
    return {
      schema_version: field("schema_version", readLiteral(1)),
      data: field("data", readData),
      warnings: field("warnings", readArrayOf(readString)),
    };
  };
}

// The backend validates nested saved records against docs/engine-demo/v1.schema.json.
export function readContractRecord<T>(recordType: string): Read<T> {
  return (value, path) => {
    readFields(value, path)("record_type", readLiteral(recordType));
    return value as T;
  };
}

export const readNextCursor = readNullable(readString);

export const readResult = readContractRecord<Result>("result");
export const readArtifact = readContractRecord<Artifact>("artifact");
export const readNormalizedRun = readContractRecord<NormalizedRun>("normalized_run");

export const readResearchPage: Read<{ results: Result[]; next_cursor: string | null }> = (
  value,
  path,
) => {
  const field = readFields(value, path);
  return {
    results: field("results", readArrayOf(readResult)),
    next_cursor: field("next_cursor", readNextCursor),
  };
};

const readSavedResultStatus: Read<SavedResultDetail["status"]> = (value, path) => {
  const field = readFields(value, path);
  return {
    origin: field("origin", readLiteral("saved_artifact", "job")),
    state: field("state", readString),
    run_id: field("run_id", readString),
  };
};

export const readSavedResultDetail: Read<SavedResultDetail> = (value, path) => {
  const field = readFields(value, path);
  return {
    result: field("result", readResult),
    run: field("run", readNormalizedRun),
    artifacts: field("artifacts", readArrayOf(readArtifact)),
    status: field("status", readSavedResultStatus),
  };
};

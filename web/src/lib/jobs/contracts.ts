import {
  readArtifact,
  readContractRecord,
  readNextCursor,
  readNormalizedRun,
  readResult,
  type Artifact,
  type Availability,
  type NormalizedRun,
  type Result,
} from "@/lib/demo/contracts";
import {
  readArrayOf,
  readBoolean,
  readFields,
  readLiteral,
  readNullable,
  readNumber,
  readString,
  ResponseShapeError,
  type Read,
} from "@/lib/parse";

export interface ReplayCatalog {
  strategy: { id: "stock-signal"; label: string; editable_fields: [] };
  datasets: {
    id: string;
    label: string;
    content_sha256: string;
    feed: string;
    synthetic: boolean;
    available: boolean;
    windows: { id: string; start: string; end_exclusive: string }[];
    cost_profile_ids: string[];
  }[];
  cost_profiles: {
    id: string;
    label: string;
    spread_bps: number;
    slippage_bps_per_fill: number;
    fee_per_share_per_fill: number;
    evidence: string;
  }[];
}

export interface JobStatus {
  record_type: "status";
  run_id: string;
  origin: "job";
  state: "queued" | "running" | "cancel_requested" | "completed" | "failed" | "cancelled";
  created_at: Availability<string>;
  started_at: Availability<string>;
  ended_at: Availability<string>;
  phase: Availability<string>;
  progress: Availability<unknown>;
  heartbeat_at: Availability<string>;
  attempt: Availability<number>;
  engine_run_id: Availability<string>;
  result_id: Availability<string>;
  failure: Availability<never> | { code: string; summary: string; at: string; retryable: boolean };
  cancellation: Availability<never> | { requested_at: string; requester_id: string };
}

export interface JobDetail {
  run: NormalizedRun;
  status: JobStatus;
  result: Result | null;
  artifacts: Artifact[];
}

const readJobStatus = readContractRecord<JobStatus>("status");

const readCatalogWindow: Read<ReplayCatalog["datasets"][number]["windows"][number]> = (
  value,
  path,
) => {
  const field = readFields(value, path);
  return {
    id: field("id", readString),
    start: field("start", readString),
    end_exclusive: field("end_exclusive", readString),
  };
};

const readCatalogDataset: Read<ReplayCatalog["datasets"][number]> = (value, path) => {
  const field = readFields(value, path);
  return {
    id: field("id", readString),
    label: field("label", readString),
    content_sha256: field("content_sha256", readString),
    feed: field("feed", readString),
    synthetic: field("synthetic", readBoolean),
    available: field("available", readBoolean),
    windows: field("windows", readArrayOf(readCatalogWindow)),
    cost_profile_ids: field("cost_profile_ids", readArrayOf(readString)),
  };
};

const readCostProfile: Read<ReplayCatalog["cost_profiles"][number]> = (value, path) => {
  const field = readFields(value, path);
  return {
    id: field("id", readString),
    label: field("label", readString),
    spread_bps: field("spread_bps", readNumber),
    slippage_bps_per_fill: field("slippage_bps_per_fill", readNumber),
    fee_per_share_per_fill: field("fee_per_share_per_fill", readNumber),
    evidence: field("evidence", readString),
  };
};

const readCatalogStrategy: Read<ReplayCatalog["strategy"]> = (value, path) => {
  const field = readFields(value, path);
  const editableFields = field("editable_fields", readArrayOf(readString));
  if (editableFields.length > 0)
    throw new ResponseShapeError(`${path}.editable_fields`, "empty array");
  return {
    id: field("id", readLiteral("stock-signal")),
    label: field("label", readString),
    editable_fields: [],
  };
};

export const readReplayCatalog: Read<ReplayCatalog> = (value, path) => {
  const field = readFields(value, path);
  return {
    strategy: field("strategy", readCatalogStrategy),
    datasets: field("datasets", readArrayOf(readCatalogDataset)),
    cost_profiles: field("cost_profiles", readArrayOf(readCostProfile)),
  };
};

export const readJobsPage: Read<{ runs: JobStatus[]; next_cursor: string | null }> = (
  value,
  path,
) => {
  const field = readFields(value, path);
  return {
    runs: field("runs", readArrayOf(readJobStatus)),
    next_cursor: field("next_cursor", readNextCursor),
  };
};

export const readJobDetail: Read<JobDetail> = (value, path) => {
  const field = readFields(value, path);
  return {
    run: field("run", readNormalizedRun),
    status: field("status", readJobStatus),
    result: field("result", readNullable(readResult)),
    artifacts: field("artifacts", readArrayOf(readArtifact)),
  };
};

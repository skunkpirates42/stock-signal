import { API_BASE } from "@/lib/api";
import { DemoNotFound, isOpaqueDemoId, type Artifact, type Availability, type NormalizedRun, type Result } from "@/lib/demo";

export interface ReplayCatalog {
  strategy: { id: "stock-signal"; label: string; editable_fields: [] };
  datasets: {
    id: string; label: string; content_sha256: string; feed: string; synthetic: boolean; available: boolean;
    windows: { id: string; start: string; end_exclusive: string }[]; cost_profile_ids: string[];
  }[];
  cost_profiles: {
    id: string; label: string; spread_bps: number; slippage_bps_per_fill: number;
    fee_per_share_per_fill: number; evidence: string;
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

interface Envelope<T> { schema_version: 1; data: T; warnings: string[] }

async function jobGet<T>(path: string): Promise<Envelope<T>> {
  const response = await fetch(`${API_BASE}/api/demo/v1${path}`, { cache: "no-store", redirect: "manual" });
  if (response.status === 404) throw new DemoNotFound("Demo job was not found");
  if (!response.ok) throw new Error(`Demo service responded ${response.status}`);
  return response.json() as Promise<Envelope<T>>;
}

export function getReplayCatalog() {
  return jobGet<ReplayCatalog>("/replay-catalog");
}

export function getJobs(cursor?: string) {
  if (cursor !== undefined && !isOpaqueDemoId(cursor)) throw new DemoNotFound("Demo cursor was not found");
  const query = new URLSearchParams({ limit: "25" });
  if (cursor) query.set("cursor", cursor);
  return jobGet<{ runs: JobStatus[]; next_cursor: string | null }>(`/runs?${query}`);
}

export function getJob(runId: string) {
  if (!isOpaqueDemoId(runId)) throw new DemoNotFound("Demo job was not found");
  return jobGet<JobDetail>(`/runs/${encodeURIComponent(runId)}`);
}

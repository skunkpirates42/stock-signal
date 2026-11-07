import type { JobStatus } from "@/lib/jobs/contracts";

const ENDED_STATES: ReadonlySet<JobStatus["state"]> = new Set(["completed", "failed", "cancelled"]);

export function phaseLabel(state: JobStatus["state"]): string {
  return ENDED_STATES.has(state) ? "Last phase" : "Phase";
}

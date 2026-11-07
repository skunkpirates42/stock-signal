import "server-only";

import { demoGet, DemoNotFound } from "@/lib/demo/server";
import { isOpaqueDemoId } from "@/lib/demo/contracts";
import { readReplayCatalog, readJobsPage, readJobDetail } from "@/lib/jobs/contracts";

export function getReplayCatalog() {
  return demoGet("/replay-catalog", readReplayCatalog);
}

export function getJobs(cursor?: string) {
  if (cursor !== undefined && !isOpaqueDemoId(cursor))
    throw new DemoNotFound("Demo cursor was not found");
  const query = new URLSearchParams({ limit: "25" });
  if (cursor) query.set("cursor", cursor);
  return demoGet(`/runs?${query}`, readJobsPage);
}

export function getJob(runId: string) {
  if (!isOpaqueDemoId(runId)) throw new DemoNotFound("Demo job was not found");
  return demoGet(`/runs/${encodeURIComponent(runId)}`, readJobDetail);
}

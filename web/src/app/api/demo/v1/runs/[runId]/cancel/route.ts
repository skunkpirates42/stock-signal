import { cancelJob } from "@/lib/job-proxy";

export async function POST(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return cancelJob(request, runId);
}

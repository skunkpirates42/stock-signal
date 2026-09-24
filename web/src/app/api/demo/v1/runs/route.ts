import { submitJob } from "@/lib/job-proxy";

export async function POST(request: Request) {
  return submitJob(request);
}

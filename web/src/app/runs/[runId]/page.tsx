import JobDetail from "@/components/JobDetail";
import { getJob } from "@/lib/jobs";
import { savedResultExists } from "@/lib/demo";
import { notFound, redirect } from "next/navigation";

export default async function RunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  let job;
  try {
    job = await getJob(runId);
  } catch (error) {
    if (!(error instanceof Error && error.name === "DemoNotFound")) throw error;
  }
  if (job) return <JobDetail detail={job.data} warnings={job.warnings} />;
  if (await savedResultExists(runId)) redirect(`/research/${encodeURIComponent(runId)}`);
  notFound();
}

import Link from "next/link";
import { notFound } from "next/navigation";
import { formatTimestamp } from "@/lib/format";
import { getJobs } from "@/lib/jobs";
import { isOpaqueDemoId } from "@/lib/demo";

export default async function RunsPage({ searchParams }: { searchParams: Promise<{ cursor?: string }> }) {
  const { cursor } = await searchParams;
  if (cursor !== undefined && !isOpaqueDemoId(cursor)) notFound();
  const { data, warnings } = await getJobs(cursor);
  return <main>
    <div className="page-head"><div><h1>Run history</h1><p className="micro">Local demo jobs</p></div><Link href="/run" className="button">New run</Link></div>
    <p className="scope-note">These are local historical replay jobs. A completed job records a simulated result; it does not authorize trading or strategy promotion.</p>
    {warnings.map((warning) => <p className="research-warning" key={warning}>{warning}</p>)}
    <div className="research-list">
      {data.runs.map((status) => <article className="card research-result" key={status.run_id}>
        <div><p className="micro">{status.state.replaceAll("_", " ")} · attempt {status.attempt.availability === "available" ? status.attempt.value : "unavailable"}</p><h2 className="num">{status.run_id}</h2></div>
        <p className="card-note">Created {status.created_at.availability === "available" ? formatTimestamp(status.created_at.value) : "at an unavailable time"}</p>
        <Link className="button research-link" href={`/runs/${status.run_id}`}>View run</Link>
      </article>)}
      {data.runs.length === 0 && <p className="scope-note">No local historical jobs have been submitted.</p>}
    </div>
    {data.next_cursor && isOpaqueDemoId(data.next_cursor) && <nav className="research-pagination" aria-label="Run history pages"><Link className="button" href={`/runs?cursor=${encodeURIComponent(data.next_cursor)}`}>Older runs</Link></nav>}
  </main>;
}

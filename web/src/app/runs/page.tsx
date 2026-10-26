import Link from "next/link";
import { notFound } from "next/navigation";
import { formatTimestamp, labelFromKey } from "@/lib/format";
import { getJobs } from "@/lib/jobs";
import { isOpaqueDemoId } from "@/lib/demo";
import PageHeader from "@/components/PageHeader";
import ScopeNote from "@/components/ScopeNote";
import Page from "@/components/Page";

export default async function RunsPage({
  searchParams,
}: {
  searchParams: Promise<{ cursor?: string }>;
}) {
  const { cursor } = await searchParams;
  if (cursor !== undefined && !isOpaqueDemoId(cursor)) notFound();
  const { data, warnings } = await getJobs(cursor);
  return (
    <Page>
      <PageHeader
        eyebrow="Local demo jobs"
        title="Run history"
        aside={
          <Link href="/run" className="button">
            New run
          </Link>
        }
      />
      <ScopeNote>
        Replays queued on this machine. A finished run is a simulation. It can’t place trades or
        promote a strategy.
      </ScopeNote>
      {warnings.map((warning) => (
        <p className="research-warning" key={warning}>
          {warning}
        </p>
      ))}
      <div className="research-list">
        {data.runs.map((status) => (
          <article className="card research-result" key={status.run_id}>
            <div>
              <p className="micro">
                {labelFromKey(status.state)} · attempt{" "}
                {status.attempt.availability === "available" ? status.attempt.value : "unavailable"}
              </p>
              <h2 className="num">{status.run_id}</h2>
            </div>
            <p className="card-note">
              Created{" "}
              {status.created_at.availability === "available"
                ? formatTimestamp(status.created_at.value)
                : "at an unavailable time"}
            </p>
            <Link className="button research-link" href={`/runs/${status.run_id}`}>
              View run
            </Link>
          </article>
        ))}
        {data.runs.length === 0 && <ScopeNote>No runs queued yet.</ScopeNote>}
      </div>
      {data.next_cursor && isOpaqueDemoId(data.next_cursor) && (
        <nav className="research-pagination" aria-label="Run history pages">
          <Link className="button" href={`/runs?cursor=${encodeURIComponent(data.next_cursor)}`}>
            Older runs
          </Link>
        </nav>
      )}
    </Page>
  );
}

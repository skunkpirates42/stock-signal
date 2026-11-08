import ServerDataRefresh from "@/components/ServerDataRefresh";
import { notFound } from "next/navigation";
import { formatTimestamp, labelFromKey } from "@/lib/format";
import { getJobs } from "@/lib/jobs/server";
import { isOpaqueDemoId } from "@/lib/demo/contracts";
import PageHeader from "@/components/PageHeader";
import ScopeNote from "@/components/ScopeNote";
import Page from "@/components/Page";
import Button from "@/components/Button";

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
      <ServerDataRefresh />
      <PageHeader
        eyebrow="Local demo jobs"
        title="Run history"
        aside={<Button href="/run">New run</Button>}
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
            <Button className="research-link" href={`/runs/${status.run_id}`}>
              View run
            </Button>
          </article>
        ))}
        {data.runs.length === 0 && <ScopeNote>No runs queued yet.</ScopeNote>}
      </div>
      {data.next_cursor && isOpaqueDemoId(data.next_cursor) && (
        <nav className="research-pagination" aria-label="Run history pages">
          <Button href={`/runs?cursor=${encodeURIComponent(data.next_cursor)}`}>Older runs</Button>
        </nav>
      )}
    </Page>
  );
}

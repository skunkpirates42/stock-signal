import Link from "next/link";
import { getResearchResults, isOpaqueDemoId } from "@/lib/demo";
import { formatCurrency, formatTimestamp } from "@/lib/format";
import { notFound } from "next/navigation";

function labels(result: Awaited<ReturnType<typeof getResearchResults>>["data"]["results"][number]) {
  const items = [];
  if (result.provenance.retrospective) items.push("Retrospective");
  if (result.provenance.synthetic) items.push("Synthetic correctness");
  return items.length ? items.join(" · ") : "Saved-source result";
}

export default async function ResearchPage({ searchParams }: { searchParams: Promise<{ cursor?: string }> }) {
  const { cursor } = await searchParams;
  if (cursor !== undefined && !isOpaqueDemoId(cursor)) notFound();
  const { data, warnings } = await getResearchResults(cursor);

  return (
    <main>
      <div className="page-head">
        <div><h1>Research</h1><p className="micro">Saved-source catalog</p></div>
        <span className="micro">{data.results.length} results on this page</span>
      </div>
      <p className="scope-note">These are read-only saved research descriptions. They do not authorize replay, execution, activation, or a profitability claim.</p>
      {warnings.map((warning) => <p className="research-warning" key={warning}>{warning}</p>)}
      <div className="research-list">
        {data.results.map((result) => {
          const pnl = result.metrics.realized_net_pnl;
          return <article className="card research-result" key={result.id}>
            <div><p className="micro">{labels(result)}</p><h2>{result.window.name} / {result.variant}</h2></div>
            <dl className="research-summary">
              <div><dt>Window</dt><dd>{formatTimestamp(result.window.start)} inclusive to {formatTimestamp(result.window.end_exclusive)} exclusive</dd></div>
              <div><dt>Realized net P&amp;L</dt><dd className="num">{pnl?.observation.availability === "available" ? formatCurrency(pnl.observation.value) : "Unavailable"}</dd></div>
              <div><dt>Accounting</dt><dd>{result.accounting.coverage}</dd></div>
            </dl>
            <Link className="button research-link" href={`/runs/${result.id}`}>View saved result<span className="sr-only"> for {result.window.name} / {result.variant}</span></Link>
          </article>;
        })}
        {data.results.length === 0 && <p className="scope-note">No saved results are indexed for this local operator.</p>}
      </div>
      {data.next_cursor && isOpaqueDemoId(data.next_cursor) && <nav className="research-pagination" aria-label="Research catalog pages"><Link className="button" href={`/research?cursor=${encodeURIComponent(data.next_cursor)}`}>Next saved results</Link></nav>}
    </main>
  );
}

import Link from "next/link";
import ResearchComparisonTable from "@/components/ResearchComparisonTable";
import { getResearchResults, isOpaqueDemoId } from "@/lib/demo";
import { warningsBeyondScopeNote } from "@/lib/research";
import { buildComparisonTable } from "@/lib/research-comparison";
import { notFound } from "next/navigation";

export default async function ResearchPage({ searchParams }: { searchParams: Promise<{ cursor?: string }> }) {
  const { cursor } = await searchParams;
  if (cursor !== undefined && !isOpaqueDemoId(cursor)) notFound();
  const { data, warnings } = await getResearchResults(cursor);
  const table = buildComparisonTable(data.results);
  const nextCursor = data.next_cursor && isOpaqueDemoId(data.next_cursor) ? data.next_cursor : null;

  return (
    <main>
      <div className="page-head">
        <div><h1>Research</h1><p className="micro">Saved-source catalog</p></div>
        <span className="micro">{data.results.length} results on this page</span>
      </div>
      <p className="scope-note">These are read-only saved research descriptions. They do not authorize replay, execution, activation, or a profitability claim.</p>
      {warningsBeyondScopeNote(warnings).map((warning) => <p className="research-warning" key={warning}>{warning}</p>)}
      {data.results.length > 0 && <ResearchComparisonTable table={table} />}
      {data.results.length === 0 && <p className="scope-note">No saved results are indexed for this local operator.</p>}
      {nextCursor && <nav className="research-pagination" aria-label="Research catalog pages">
        <p className="note">This table compares the results on this page only. More saved results are on the next page.</p>
        <Link className="button" href={`/research?cursor=${encodeURIComponent(nextCursor)}`}>Next saved results</Link>
      </nav>}
    </main>
  );
}

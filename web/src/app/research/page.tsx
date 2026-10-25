import Link from "next/link";
import ResearchComparisonTable from "@/components/ResearchComparisonTable";
import { getResearchResults, isOpaqueDemoId } from "@/lib/demo";
import { warningsBeyondScopeNote } from "@/lib/research";
import { buildComparisonTable } from "@/lib/research-comparison";
import { notFound } from "next/navigation";
import PageHeader from "@/components/PageHeader";
import ScopeNote from "@/components/ScopeNote";

export default async function ResearchPage({ searchParams }: { searchParams: Promise<{ cursor?: string }> }) {
  const { cursor } = await searchParams;
  if (cursor !== undefined && !isOpaqueDemoId(cursor)) notFound();
  const { data, warnings } = await getResearchResults(cursor);
  const table = buildComparisonTable(data.results);
  const nextCursor = data.next_cursor && isOpaqueDemoId(data.next_cursor) ? data.next_cursor : null;

  return (
    <main>
      <PageHeader eyebrow="Saved-source catalog" title="Research" aside={<span className="micro">{data.results.length} results on this page</span>} />
      <ScopeNote>Saved research results, read-only. Nothing here runs a replay or a trade, and none of it shows a strategy is profitable.</ScopeNote>
      {warningsBeyondScopeNote(warnings).map((warning) => <p className="research-warning" key={warning}>{warning}</p>)}
      {data.results.length > 0 && <ResearchComparisonTable table={table} />}
      {data.results.length === 0 && <ScopeNote>No saved results yet.</ScopeNote>}
      {nextCursor && <nav className="research-pagination" aria-label="Research catalog pages">
        <p className="note">This table compares the results on this page only. More saved results are on the next page.</p>
        <Link className="button" href={`/research?cursor=${encodeURIComponent(nextCursor)}`}>Next saved results</Link>
      </nav>}
    </main>
  );
}

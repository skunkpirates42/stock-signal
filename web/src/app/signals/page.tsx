import ServerDataRefresh from "@/components/ServerDataRefresh";
import Link from "next/link";
import { searchSignals } from "@/lib/api";
import { parseSignalQuery, signalQueryParams, type SignalSearchParams } from "@/lib/signalSearch";
import SignalList from "@/components/SignalList";
import ScopeNote from "@/components/ScopeNote";
import PageHeader from "@/components/PageHeader";
import Page from "@/components/Page";

export default async function SignalsPage({
  searchParams,
}: {
  searchParams: Promise<SignalSearchParams>;
}) {
  const params = await searchParams;
  let query;
  try {
    query = parseSignalQuery(params);
  } catch (error) {
    return (
      <Page>
        <PageHeader title="Signals" />
        <p role="alert">
          Invalid signal filters. {error instanceof Error ? error.message : "Check the URL."}
        </p>
        <Link href={params.source === "all" ? "/signals?source=all" : "/signals"}>
          Reset filters
        </Link>
      </Page>
    );
  }
  const result = await searchSignals(query);

  return (
    <Page>
      <ServerDataRefresh />
      <PageHeader
        title="Signals"
        aside={<span className="micro">{result.total} matching signals</span>}
      />
      <ScopeNote>
        Searching all {result.scope_total} {query.source === "live" ? "live" : "journal"} signals in
        this view.
        {query.source === "live"
          ? " Backtest replay and unknown-source signals are excluded."
          : " All recorded sources are included; replay signals may come from a different period."}
        {
          " Dates use UTC signal-bar time, or the recorded time when no bar time is available. Both selected dates are included."
        }
      </ScopeNote>
      <SignalList key={signalQueryParams(query).toString()} result={result} query={query} />
    </Page>
  );
}

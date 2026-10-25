import { getOpenPositions, getTrades } from "@/lib/api";
import OpenPositions from "@/components/OpenPositions";
import FillsTable from "@/components/FillsTable";
import ScopeNote from "@/components/ScopeNote";
import PageHeader from "@/components/PageHeader";
import Page from "@/components/Page";

export default async function PositionsPage({
  searchParams,
}: {
  searchParams: Promise<{ source?: string }>;
}) {
  const { source } = await searchParams;
  const scope = source === "all" ? undefined : "live";

  const [scopedPositions, unknownPositions, trades] = await Promise.all([
    getOpenPositions(scope ?? "all"),
    scope === "live" ? getOpenPositions("unknown") : Promise.resolve([]),
    getTrades({ source: scope, limit: 50 }),
  ]);
  const positions = [...scopedPositions, ...unknownPositions];
  const closedTrades = trades.filter((trade) => trade.outcome !== "OPEN");
  const now = new Date();

  return (
    <Page>
      <PageHeader title="Positions" aside={<span className="micro">{positions.length} open</span>} />
      <ScopeNote>
        {scope === "live"
          ? "Live open positions and closed trades, plus older positions with an unknown source. Unknown positions can block trading until they’re reconciled. Backtest replay rows are hidden."
          : `All sources, including replay and older positions with an unknown source. ${closedTrades.length} recent closed trades.`}
      </ScopeNote>
      <OpenPositions positions={positions} now={now} />
      <FillsTable trades={closedTrades} />
    </Page>
  );
}

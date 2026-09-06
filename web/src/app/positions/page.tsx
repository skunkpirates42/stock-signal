import { getOpenPositions, getTrades } from "@/lib/api";
import OpenPositions from "@/components/OpenPositions";
import FillsTable from "@/components/FillsTable";
import ScopeNote from "@/components/ScopeNote";

export default async function PositionsPage({
  searchParams,
}: {
  searchParams: Promise<{ source?: string }>;
}) {
  const { source } = await searchParams;
  const scope = source === "all" ? undefined : "live";

  const [positions, trades] = await Promise.all([
    getOpenPositions(scope ?? "all"),
    getTrades({ source: scope, limit: 50 }),
  ]);
  const closedTrades = trades.filter((trade) => trade.outcome !== "OPEN");
  const now = new Date();

  return (
    <main>
      <div className="page-head">
        <h1>Positions</h1>
        <span className="micro">{positions.length} open</span>
      </div>
      <ScopeNote>
        {scope === "live"
          ? "Showing live open positions and live closed trades only. Backtest replay rows are excluded from this view."
          : `Showing all sources, including replay and unknown historical positions. ${closedTrades.length} recent closed trades.`}
      </ScopeNote>
      <OpenPositions positions={positions} now={now} />
      <FillsTable trades={closedTrades} />
    </main>
  );
}

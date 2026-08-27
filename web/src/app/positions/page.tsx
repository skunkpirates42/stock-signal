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
    getOpenPositions(),
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
          : `Showing live open positions and ${closedTrades.length} closed trades, live and backtest replay combined. Open positions are always live; replay closed trades come from a different period.`}
      </ScopeNote>
      <OpenPositions positions={positions} now={now} />
      <FillsTable trades={closedTrades} />
    </main>
  );
}

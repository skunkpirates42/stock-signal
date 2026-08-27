import { getOpenPositions, getTrades } from "@/lib/api";
import PositionsTable from "@/components/PositionsTable";
import FillsTable from "@/components/FillsTable";
import ScopeNote from "@/components/ScopeNote";

export default async function PositionsPage() {
  const [positions, trades] = await Promise.all([
    getOpenPositions(),
    getTrades({ source: "live", limit: 50 }),
  ]);
  const closedTrades = trades.filter((trade) => trade.outcome !== "OPEN");
  const now = new Date();

  return (
    <main className="page-content">
      <h1>Positions</h1>
      <ScopeNote>
        Showing live open positions and live closed trades only. Backtest replay rows are
        excluded from this view.
      </ScopeNote>
      <PositionsTable positions={positions} now={now} />
      <FillsTable trades={closedTrades} />
    </main>
  );
}

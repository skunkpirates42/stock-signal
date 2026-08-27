import { getOpenPositions, getTrades } from "@/lib/api";
import PositionsTable from "@/components/PositionsTable";
import FillsTable from "@/components/FillsTable";

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
      <PositionsTable positions={positions} now={now} />
      <FillsTable trades={closedTrades} />
    </main>
  );
}

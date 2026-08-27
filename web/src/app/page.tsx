import { getMetrics } from "@/lib/api";
import { formatCurrency, formatPercent } from "@/lib/format";
import ProvenanceBand from "@/components/ProvenanceBand";
import StatTile from "@/components/StatTile";
import CostAdjustedExpectancy from "@/components/CostAdjustedExpectancy";
import BreakdownTable from "@/components/BreakdownTable";

export default async function OverviewPage({
  searchParams,
}: {
  searchParams: Promise<{ source?: string }>;
}) {
  const { source } = await searchParams;
  const scope = source === "all" ? undefined : "live";
  const metrics = await getMetrics(scope);

  return (
    <main className="page-content">
      <ProvenanceBand source={scope === undefined ? "all" : "live"} nClosed={metrics.n_closed} />

      <div className="stat-grid">
        <StatTile
          label="Win rate"
          value={formatPercent(metrics.win_rate)}
          tone={metrics.win_rate >= 0.5 ? "positive" : "negative"}
        />
        <StatTile
          label="Expectancy"
          value={formatCurrency(metrics.expectancy)}
          tone={metrics.expectancy >= 0 ? "positive" : "negative"}
        />
        <StatTile
          label="Total P&L"
          value={formatCurrency(metrics.total_pnl)}
          tone={metrics.total_pnl >= 0 ? "positive" : "negative"}
        />
        <StatTile
          label="Max drawdown"
          value={`${formatCurrency(metrics.max_drawdown)} (${formatPercent(metrics.max_drawdown_pct)})`}
          tone="negative"
        />
        <StatTile label="Closed trades" value={String(metrics.n_closed)} />
        <StatTile label="Open positions" value={String(metrics.n_open)} />
      </div>

      <CostAdjustedExpectancy grossExpectancy={metrics.expectancy} />

      <BreakdownTable title="By regime" rows={metrics.by_regime} />
      <BreakdownTable title="By ticker" rows={metrics.by_ticker} />
    </main>
  );
}

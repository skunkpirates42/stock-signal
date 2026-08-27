import { getMetrics } from "@/lib/api";
import { formatCurrency, formatPercent, formatRatio } from "@/lib/format";
import ProvenanceBand from "@/components/ProvenanceBand";
import HeroStat from "@/components/HeroStat";
import StatTile from "@/components/StatTile";
import WinLossCard from "@/components/WinLossCard";
import RMultipleCard from "@/components/RMultipleCard";
import CostAdjustedExpectancy from "@/components/CostAdjustedExpectancy";
import BreakdownTable from "@/components/BreakdownTable";
import EquityCurve from "@/components/EquityCurve";

export default async function OverviewPage({
  searchParams,
}: {
  searchParams: Promise<{ source?: string }>;
}) {
  const { source } = await searchParams;
  const scope = source === "all" ? undefined : "live";
  const bandSource = scope === undefined ? "all" : "live";

  const [metrics, liveMetrics] = await Promise.all([
    getMetrics(scope),
    bandSource === "live" ? Promise.resolve(null) : getMetrics("live"),
  ]);
  const nLiveClosed = liveMetrics === null ? metrics.n_closed : liveMetrics.n_closed;

  return (
    <main className="canvas">
      <HeroStat
        label="Total P&L"
        value={formatCurrency(metrics.total_pnl)}
        tone={metrics.total_pnl >= 0 ? "positive" : "negative"}
        qualifier={
          <>
            <span className="num">{metrics.n_closed}</span> closed ·{" "}
            <span className="num">{formatPercent(metrics.win_rate)}</span> win ·{" "}
            <span className="num">{metrics.n_open}</span> open
          </>
        }
      >
        <ProvenanceBand source={bandSource} nClosed={metrics.n_closed} nLiveClosed={nLiveClosed} />
      </HeroStat>

      <div className="grid-8-4">
        <EquityCurve points={metrics.equity} />
        <WinLossCard
          nWins={metrics.n_wins}
          nLosses={metrics.n_losses}
          winRate={metrics.win_rate}
          avgWin={metrics.avg_win}
          avgLoss={metrics.avg_loss}
        />
      </div>

      <div className="stat-grid">
        <StatTile
          label="Expectancy"
          value={formatCurrency(metrics.expectancy)}
          tone={metrics.expectancy >= 0 ? "positive" : "negative"}
        />
        <StatTile
          label="Profit factor"
          value={metrics.profit_factor === null ? "—" : formatRatio(metrics.profit_factor)}
          tone={metrics.profit_factor !== null && metrics.profit_factor >= 1 ? "positive" : "negative"}
        />
        <StatTile
          label="Max drawdown"
          value={`${formatCurrency(-metrics.max_drawdown)} (${formatPercent(metrics.max_drawdown_pct)})`}
          tone="negative"
        />
        <StatTile label="Avg bars held" value={formatRatio(metrics.avg_bars_held)} />
      </div>

      <div className="grid-6-6">
        <CostAdjustedExpectancy grossExpectancy={metrics.expectancy} />
        <RMultipleCard
          avgR={metrics.avg_r_multiple}
          avgWinR={metrics.avg_win_r}
          avgLossR={metrics.avg_loss_r}
        />
      </div>

      <div className="grid-6-6">
        <BreakdownTable title="By regime" rows={metrics.by_regime} />
        <BreakdownTable title="By ticker" rows={metrics.by_ticker} />
      </div>
    </main>
  );
}

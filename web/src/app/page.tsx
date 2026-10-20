import { getMetrics } from "@/lib/api";
import { formatCurrency, formatPercent, formatPrice, formatRatio, toneForSign } from "@/lib/format";
import { observedOrNull } from "@/lib/metrics";
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
  const winRate = observedOrNull(metrics.n_closed, metrics.win_rate);
  const expectancy = observedOrNull(metrics.n_closed, metrics.expectancy);

  return (
    <main>
      <HeroStat
        label="Closed-trade net P&L"
        value={formatCurrency(metrics.total_pnl)}
        tone={toneForSign(metrics.total_pnl)}
        qualifier={
          <>
            <span className="num">{metrics.n_closed}</span> closed ·{" "}
            <span className="num">{formatPercent(winRate)}</span> win ·{" "}
            <span className="num">{metrics.n_open}</span> open
          </>
        }
      >
        <ProvenanceBand source={bandSource} nClosed={metrics.n_closed} nLiveClosed={nLiveClosed} />
      </HeroStat>

      <p className="note">{metrics.metric_basis}</p>
      <div className="grid-8-4">
        <EquityCurve points={metrics.equity} />
        <WinLossCard
          nWins={metrics.n_wins}
          nLosses={metrics.n_losses}
          nBreakeven={metrics.n_breakeven}
          winRate={winRate}
          avgWin={observedOrNull(metrics.n_wins, metrics.avg_win)}
          avgLoss={observedOrNull(metrics.n_losses, metrics.avg_loss)}
        />
      </div>

      <div className="stat-grid">
        <StatTile
          label="Expectancy"
          value={formatCurrency(expectancy)}
          tone={toneForSign(expectancy)}
        />
        <StatTile
          label="Profit factor"
          value={metrics.profit_factor === null ? "—" : formatRatio(metrics.profit_factor)}
          tone={metrics.profit_factor === null ? "muted" : metrics.profit_factor >= 1 ? "positive" : "negative"}
        />
        <StatTile
          label="Max drawdown"
          value={`${formatPrice(metrics.max_drawdown)} (${formatPercent(metrics.max_drawdown_pct)})`}
          tone={toneForSign(-metrics.max_drawdown)}
        />
        <StatTile label="Avg bars held" value={formatRatio(observedOrNull(metrics.n_closed, metrics.avg_bars_held))} />
      </div>

      <div className="grid-6-6">
        <CostAdjustedExpectancy recordedExpectancy={expectancy} />
        <RMultipleCard
          avgR={observedOrNull(metrics.n_closed, metrics.avg_r_multiple)}
          avgWinR={observedOrNull(metrics.n_wins, metrics.avg_win_r)}
          avgLossR={observedOrNull(metrics.n_losses, metrics.avg_loss_r)}
        />
      </div>

      <div className="grid-6-6">
        <BreakdownTable title="By regime" rows={metrics.by_regime} />
        <BreakdownTable title="By ticker" rows={metrics.by_ticker} />
      </div>
    </main>
  );
}

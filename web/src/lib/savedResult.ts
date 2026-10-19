import type { Artifact, Metric } from "@/lib/demo";
import { toneForSign, type Tone } from "@/lib/format";
import { formatMetricAmount } from "@/lib/metrics";

export interface HeadlineFigure {
  label: string;
  value: string;
  tone: Tone;
  note?: string;
}

export interface MetricRow {
  name: string;
  label: string;
  value: string;
  ownBasis: string | null;
}

export interface MetricGroup {
  title: string;
  basis: string | null;
  rows: MetricRow[];
}

export interface UntrackedComponent {
  label: string;
  reason: string;
}

const REALIZED_METRICS = ["realized_net_pnl", "gross_pnl", "recorded_costs", "realized_max_drawdown", "closed_trades", "censored_positions"];
const MARKED_METRICS = ["marked_net_pnl", "marked_max_drawdown", "marked_net_per_session", "max_gross_exposure"];
const COST_COMPONENTS: Record<string, string> = {
  spread_cost: "spread",
  slippage_cost: "slippage",
  fees: "fees",
  borrow_cost: "borrow",
  dividend_cashflow: "dividends",
};

const ARTIFACT_KINDS = {
  accounting: ["accounting", "cashflows"],
  quality: ["diagnostics"],
  data: ["data_health", "dataset_metadata"],
};

export function metricLabel(name: string): string {
  return name.replaceAll("_", " ");
}

export function metricValue(name: string, metric: Metric | undefined): string {
  if (!metric) return "Unavailable";
  if (metric.observation.availability !== "available") return `Unavailable: ${metric.observation.detail}`;
  if (metric.unit === "USD" || metric.unit === "USD/session") return formatMetricAmount(name, metric.observation.value);
  return String(metric.observation.value);
}

function signedTone(metric: Metric | undefined): Tone {
  return toneForSign(metric?.observation.availability === "available" ? metric.observation.value : null);
}

export function headlineFigures(metrics: Record<string, Metric>): HeadlineFigure[] {
  return [
    { label: "Realized net P&L", value: metricValue("realized_net_pnl", metrics.realized_net_pnl), tone: signedTone(metrics.realized_net_pnl) },
    { label: "Closed trades", value: metricValue("closed_trades", metrics.closed_trades), tone: "muted" },
    { label: "Realized max drawdown", value: metricValue("realized_max_drawdown", metrics.realized_max_drawdown), tone: "muted" },
    { label: "Marked net P&L", value: metricValue("marked_net_pnl", metrics.marked_net_pnl), tone: signedTone(metrics.marked_net_pnl), note: "Marked to latest close" },
    { label: "Marked max drawdown", value: metricValue("marked_max_drawdown", metrics.marked_max_drawdown), tone: "muted", note: "Marked to latest close" },
  ];
}

function sharedBasis(metrics: Record<string, Metric>, names: string[]): string | null {
  const counts = new Map<string, number>();
  for (const name of names) {
    const basis = metrics[name]?.basis;
    if (basis) counts.set(basis, (counts.get(basis) ?? 0) + 1);
  }
  let best: string | null = null;
  for (const [basis, count] of counts) {
    if (best === null || count > counts.get(best)!) best = basis;
  }
  return best;
}

function metricGroup(title: string, metrics: Record<string, Metric>, names: string[]): MetricGroup {
  const basis = sharedBasis(metrics, names);
  return {
    title,
    basis,
    rows: names.map((name) => {
      const ownBasis = metrics[name]?.basis ?? null;
      return { name, label: metricLabel(name), value: metricValue(name, metrics[name]), ownBasis: ownBasis === basis ? null : ownBasis };
    }),
  };
}

export function savedMetricGroups(metrics: Record<string, Metric>): MetricGroup[] {
  const trackedCosts = Object.keys(COST_COMPONENTS).filter((name) => metrics[name]?.observation.availability === "available");
  const groups = [metricGroup("Realized", metrics, REALIZED_METRICS), metricGroup("Marked", metrics, MARKED_METRICS)];
  return trackedCosts.length ? [...groups, metricGroup("Cost components", metrics, trackedCosts)] : groups;
}

export function untrackedCostComponents(metrics: Record<string, Metric>): UntrackedComponent[] {
  return Object.entries(COST_COMPONENTS).flatMap(([name, label]) => {
    const metric = metrics[name];
    if (!metric) return [{ label, reason: "No saved metric." }];
    if (metric.observation.availability === "available") return [];
    return [{ label, reason: `${metric.observation.detail} ${metric.basis}` }];
  });
}

export function groupArtifactsByKind(artifacts: Artifact[]) {
  const known = Object.values(ARTIFACT_KINDS).flat();
  return {
    accounting: artifacts.filter((item) => ARTIFACT_KINDS.accounting.includes(item.kind)),
    quality: artifacts.filter((item) => ARTIFACT_KINDS.quality.includes(item.kind)),
    data: artifacts.filter((item) => ARTIFACT_KINDS.data.includes(item.kind)),
    reproducibility: artifacts.filter((item) => !known.includes(item.kind)),
  };
}

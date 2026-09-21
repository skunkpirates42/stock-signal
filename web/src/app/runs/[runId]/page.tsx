import Link from "next/link";
import { artifactHref, availabilityText, getSavedResult, type Availability, type Metric } from "@/lib/demo";
import { formatCurrency, formatTimestamp } from "@/lib/format";
import { notFound } from "next/navigation";

const METRICS = ["realized_net_pnl", "gross_pnl", "recorded_costs", "realized_max_drawdown", "marked_net_pnl", "marked_max_drawdown", "marked_net_per_session", "max_gross_exposure", "closed_trades", "censored_positions", "borrow_cost", "dividend_cashflow", "spread_cost", "slippage_cost", "fees"];

function metricValue(metric: Metric | undefined) {
  if (!metric) return "Unavailable";
  if (metric.observation.availability !== "available") return `Unavailable: ${metric.observation.detail}`;
  if (metric.unit === "USD" || metric.unit === "USD/session") return formatCurrency(metric.observation.value);
  return String(metric.observation.value);
}

function field(label: string, value: Availability<string>) {
  return <div><dt>{label}</dt><dd className="config-value">{availabilityText(value)}</dd></div>;
}

export default async function SavedRunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId: resultId } = await params;
  let detail;
  try {
    detail = await getSavedResult(resultId);
  } catch (error) {
    if (error instanceof Error && error.name === "DemoNotFound") notFound();
    throw error;
  }
  const { data, warnings } = detail;
  const { result, run, artifacts } = data;

  return <main>
    <Link className="micro" href="/research">← Saved research</Link>
    <div className="page-head run-head">
      <div><p className="micro">{result.provenance.synthetic ? "Synthetic correctness" : result.provenance.retrospective ? "Retrospective" : "Saved-source result"}</p><h1>{result.window.name} / {result.variant}</h1></div>
      <span className="micro">Saved result</span>
    </div>
    <p className="scope-note">This route token is the A3 result ID, because A3 exposes no run lookup endpoint. Saved run ID: <span className="num">{run.id}</span>. The status is a completed artifact reference, not evidence that a job ran or that this configuration is approved.</p>
    {warnings.map((warning) => <p className="research-warning" key={warning}>{warning}</p>)}

    <section className="card"><h2>Comparison</h2><dl className="research-summary comparison-summary">
      <div><dt>Window</dt><dd>{result.window.name} ({result.window.role})</dd></div>
      <div><dt>Evaluation</dt><dd>{result.provenance.evaluation}</dd></div>
      <div><dt>Period</dt><dd>{formatTimestamp(result.window.start)} inclusive to {formatTimestamp(result.window.end_exclusive)} exclusive</dd></div>
      <div><dt>Result ID</dt><dd className="num">{result.id}</dd></div>
    </dl></section>

    <section className="card"><h2>Saved metrics</h2><p className="card-note">Values are displayed as supplied by the saved Python projection; this page does not recompute P&amp;L.</p><dl className="metric-grid">
      {METRICS.map((name) => <div key={name}><dt>{name.replaceAll("_", " ")}</dt><dd className="num">{metricValue(result.metrics[name])}</dd><small>{result.metrics[name]?.basis}</small></div>)}
    </dl></section>

    <section className="card"><h2>Exact saved configuration</h2><dl className="config-grid">
      {field("Strategy version", run.strategy_version)} {field("Dataset SHA-256", run.dataset_sha256)}
      {field("Selected-data SHA-256", run.selected_data_sha256)} {field("Feed", run.feed)}
      {field("Fill policy", run.fill_policy)} {field("Session policy", run.session_policy)}
      {field("Revision", run.code.revision)} {field("Source SHA-256", run.code.source_sha256)}
      {field("Working diff SHA-256", run.code.working_diff_sha256)}
      <div><dt>Dataset ID</dt><dd className="config-value">{run.dataset_id}</dd></div>
      <div><dt>Selected window</dt><dd>{formatTimestamp(run.window.start)} inclusive to {formatTimestamp(run.window.end_exclusive)} exclusive ({run.window.role})</dd></div>
      {Object.entries(run.observed_bounds).map(([name, value]) => <div key={name}><dt>Observed {name.replaceAll("_", " ")}</dt><dd className="config-value">{availabilityText(value)}</dd></div>)}
      <div><dt>Symbols</dt><dd>{run.symbols.join(", ")}</dd></div><div><dt>Cost policy</dt><dd>{run.cost_policy.id}: {run.cost_policy.spread_bps} spread bps, {run.cost_policy.slippage_bps_per_fill} slippage bps/fill, {run.cost_policy.fee_per_share_per_fill} fee/share.</dd></div>
      <div><dt>Cost evidence</dt><dd>{run.cost_policy.evidence}</dd></div>
      <div><dt>Accounting</dt><dd>{run.accounting.mode}; {run.accounting.coverage}; {availabilityText(run.accounting.version)}</dd></div>
    </dl></section>

    <section className="card"><h2>Marked metrics and accounting limits</h2><p className="card-note">Marked values use the saved marked basis and are distinct from realized results.</p><ul className="research-listing">{result.limitations.map((item) => <li key={item}>{item}</li>)}{result.accounting.unresolved.map((item) => <li key={item}>Unresolved accounting: {item}</li>)}</ul></section>
    <section className="card"><h2>Artifacts</h2>{artifacts.length ? <ul className="artifact-list">{artifacts.map((artifact) => <li key={artifact.id}><a href={artifactHref(result.id, artifact.id)}>{artifact.kind}</a> <span className="micro">{artifact.mime_type} · {artifact.byte_size} bytes · {artifact.sha256}</span></li>)}</ul> : <p className="card-note">No safe, indexed artifacts are available for this saved result.</p>}</section>
  </main>;
}

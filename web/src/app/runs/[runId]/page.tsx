import Link from "next/link";
import JobDetail from "@/components/JobDetail";
import { getJob } from "@/lib/jobs";
import { artifactHref, availabilityText, getSavedDiagnostics, getSavedResult, type Artifact, type Availability, type Metric } from "@/lib/demo";
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

function countList(counts: Record<string, number>) {
  const entries = Object.entries(counts);
  return entries.length
    ? <dl className="audit-counts">{entries.map(([name, count]) => <div key={name}><dt>{name.replaceAll("_", " ")}</dt><dd className="num">{count}</dd></div>)}</dl>
    : <p className="card-note">The saved count map is present and empty.</p>;
}

function artifactList(resultId: string, artifacts: Artifact[]) {
  return artifacts.length ? <ul className="artifact-list">{artifacts.map((artifact) => <li key={artifact.id}>
    <a href={artifactHref(resultId, artifact.id)}>{artifact.kind.replaceAll("_", " ")}</a>
    <span className="micro">{artifact.mime_type} · {artifact.byte_size} bytes · SHA-256 {artifact.sha256}</span>
  </li>)}</ul> : <p className="card-note">No indexed artifacts in this category.</p>;
}

export default async function SavedRunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId: resultId } = await params;
  let job;
  try {
    job = await getJob(resultId);
  } catch (error) {
    if (!(error instanceof Error && error.name === "DemoNotFound")) throw error;
  }
  if (job) return <JobDetail detail={job.data} warnings={job.warnings} />;
  let detail;
  try {
    detail = await getSavedResult(resultId);
  } catch (error) {
    if (error instanceof Error && error.name === "DemoNotFound") notFound();
    throw error;
  }
  const { data, warnings } = detail;
  const { result, run, artifacts } = data;
  const diagnostics = await getSavedDiagnostics(result.id, artifacts);
  const artifactsByKind = {
    accounting: artifacts.filter((item) => ["accounting", "cashflows"].includes(item.kind)),
    quality: artifacts.filter((item) => item.kind === "diagnostics"),
    data: artifacts.filter((item) => ["data_health", "dataset_metadata"].includes(item.kind)),
    reproducibility: artifacts.filter((item) => !["accounting", "cashflows", "diagnostics", "data_health", "dataset_metadata"].includes(item.kind)),
  };

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

    <section className="card"><h2>Accounting audit</h2><p className="card-note">Every amount below is a saved Python observation. Missing cost attribution remains unavailable and is never filled with zero.</p><dl className="metric-grid audit-metrics">
      {["gross_pnl", "realized_net_pnl", "recorded_costs", "spread_cost", "slippage_cost", "fees", "borrow_cost", "dividend_cashflow"].map((name) => <div key={name}><dt>{name.replaceAll("_", " ")}</dt><dd className="num">{metricValue(result.metrics[name])}</dd><small>{result.metrics[name]?.basis ?? "No saved basis."}</small></div>)}
    </dl><dl className="config-grid"><div><dt>Coverage</dt><dd>{result.accounting.coverage}</dd></div><div><dt>Mode</dt><dd>{result.accounting.mode}</dd></div><div><dt>Policy version</dt><dd>{availabilityText(result.accounting.version)}</dd></div></dl>
      {result.accounting.unresolved.length ? <ul className="research-listing">{result.accounting.unresolved.map((item) => <li key={item}>Unresolved accounting: {item}</li>)}</ul> : <p className="card-note">The saved result declares no unresolved accounting fields.</p>}
    </section>

    <section className="card"><h2>Signal-quality audit</h2><p className="card-note">These are saved aggregate counts, not live signals and not counts recomputed by the browser.</p>
      {diagnostics.availability === "available" ? <div className="audit-columns"><div><h3>Execution and skip reasons</h3>{countList(diagnostics.value.signal_execution_reasons)}</div><div><h3>Candidate gate checks</h3>{countList(diagnostics.value.candidate_gate_checks)}</div></div> : <p className="unavailable-note">Unavailable: {diagnostics.detail}</p>}
      <p className="unavailable-note"><strong>Detailed filters unavailable.</strong> Ticker, direction, regime, gate-decision, and rejection-reason queries require the bounded R1 read model.</p>
    </section>

    <section className="card"><h2>Saved data health</h2><dl className="config-grid">
      {field("Recorded feed", run.feed)}<div><dt>Saved symbols</dt><dd>{run.symbols.join(", ") || "Unavailable: no symbols were recorded."}</dd></div>
      {Object.entries(run.observed_bounds).map(([name, value]) => <div key={name}><dt>Saved observed {name.replaceAll("_", " ")}</dt><dd>{availabilityText(value)}</dd></div>)}
    </dl>{artifactsByKind.data.length ? <p className="card-note">Indexed data-health evidence is linked in the artifact inventory below. Its presence does not make fields available in this normalized view.</p> : <p className="unavailable-note">Unavailable: no indexed data-health or dataset-metadata artifact is linked to this result.</p>}
      <p className="unavailable-note"><strong>Source-specific health unavailable.</strong> Latest bar, stale fraction, missing sessions, and calendar alignment require the R2 read model; this page does not infer them.</p>
    </section>

    <section className="card"><h2>Shadow comparison</h2><p className="unavailable-note"><strong>Unavailable.</strong> A read-only baseline/candidate comparison requires stable T05 artifacts and the R3 adapter. No portfolio action is available here.</p></section>

    <section className="card"><h2>Limitations</h2><p className="card-note">Marked values use the saved marked basis and are distinct from realized results.</p>{result.limitations.length ? <ul className="research-listing">{result.limitations.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="card-note">No additional saved limitations were supplied.</p>}</section>

    <section className="card"><h2>Artifact inventory</h2><p className="card-note">Only allowlisted, result-scoped files are linked. An indexed file is evidence of availability, not proof that its contents were normalized above.</p><div className="artifact-groups">
      <div><h3>Accounting evidence</h3>{artifactList(result.id, artifactsByKind.accounting)}</div>
      <div><h3>Signal-quality evidence</h3>{artifactList(result.id, artifactsByKind.quality)}</div>
      <div><h3>Data-health evidence</h3>{artifactList(result.id, artifactsByKind.data)}</div>
      <div><h3>Reproducibility and results</h3>{artifactList(result.id, artifactsByKind.reproducibility)}</div>
    </div>{artifacts.length === 0 && <p className="unavailable-note">No safe, indexed artifacts are available for this saved result.</p>}</section>
  </main>;
}

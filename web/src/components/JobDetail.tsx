import Link from "next/link";
import JobActions from "@/components/JobActions";
import { availabilityText, type Availability, type Metric } from "@/lib/demo";
import type { JobDetail as Detail } from "@/lib/jobs";
import { formatCurrency, formatTimestamp } from "@/lib/format";

function recorded<T>(value: Availability<T>, format: (item: T) => string): string {
  return value.availability === "available" ? format(value.value) : `Unavailable: ${value.detail}`;
}

function metric(metric: Metric | undefined): string {
  if (!metric) return "Unavailable: no saved metric.";
  if (metric.observation.availability !== "available") return `Unavailable: ${metric.observation.detail}`;
  if (metric.unit === "USD") return formatCurrency(metric.observation.value);
  if (metric.unit === "USD/session") return `${formatCurrency(metric.observation.value)}/session`;
  return `${metric.observation.value} ${metric.unit}`;
}

export default function JobDetail({ detail, warnings }: { detail: Detail; warnings: string[] }) {
  const { run, status, result, artifacts } = detail;
  const label = run.provenance.synthetic ? "Synthetic correctness" : run.provenance.retrospective ? "Retrospective market data" : "Historical simulation";
  return <main>
    <Link className="micro" href="/runs">← Run history</Link>
    <div className="page-head run-head"><div><p className="micro">{label}</p><h1>Historical run</h1></div><span className="micro">{status.state.replaceAll("_", " ")}</span></div>
    <p className="scope-note">This local replay is paper-only. Its outcome cannot activate collection, place an order, or promote a strategy.</p>
    {warnings.map((warning) => <p className="research-warning" key={warning}>{warning}</p>)}
    <section className="card"><h2>Progress</h2><dl className="config-grid">
      <div><dt>State</dt><dd>{status.state.replaceAll("_", " ")}</dd></div>
      <div><dt>Phase</dt><dd>{recorded(status.phase, String)}</dd></div>
      <div><dt>Attempt</dt><dd>{recorded(status.attempt, String)}</dd></div>
      <div><dt>Created</dt><dd>{recorded(status.created_at, formatTimestamp)}</dd></div>
      <div><dt>Started</dt><dd>{recorded(status.started_at, formatTimestamp)}</dd></div>
      <div><dt>Last heartbeat</dt><dd>{recorded(status.heartbeat_at, formatTimestamp)}</dd></div>
      <div><dt>Ended</dt><dd>{recorded(status.ended_at, formatTimestamp)}</dd></div>
      <div><dt>Run ID</dt><dd className="num">{status.run_id}</dd></div>
    </dl>
      {status.state === "queued" && <p className="card-note">Waiting for the separate local worker to claim this run.</p>}
      {status.state === "cancel_requested" && <p className="card-note">Cancellation requested. The worker is stopping the current attempt.</p>}
      {status.state === "cancelled" && <p className="card-note">This run was cancelled before a result was published.</p>}
      {status.state === "failed" && <p role="alert" className="research-warning">{("code" in status.failure) ? `${status.failure.code}: ${status.failure.summary}` : "The run failed without a recorded summary."}</p>}
      <JobActions status={status} />
    </section>
    <section className="card"><h2>Exact queued configuration</h2><dl className="config-grid">
      <div><dt>Strategy</dt><dd>{run.strategy_id} · {availabilityText(run.strategy_version)}</dd></div>
      <div><dt>Variant</dt><dd>{run.variant}</dd></div>
      <div><dt>Dataset ID</dt><dd className="num">{run.dataset_id}</dd></div>
      <div><dt>Dataset digest</dt><dd className="num">{availabilityText(run.dataset_sha256)}</dd></div>
      <div><dt>Selected data digest</dt><dd className="num">{availabilityText(run.selected_data_sha256)}</dd></div>
      <div><dt>Window</dt><dd>{run.window.name} ({run.window.role}): {formatTimestamp(run.window.start)} inclusive to {formatTimestamp(run.window.end_exclusive)} exclusive</dd></div>
      <div><dt>Symbols</dt><dd>{run.symbols.join(", ") || "Unavailable: no symbols were recorded."}</dd></div>
      {Object.entries(run.observed_bounds).map(([name, value]) => <div key={name}><dt>Observed {name.replaceAll("_", " ")}</dt><dd>{availabilityText(value)}</dd></div>)}
      <div><dt>Feed</dt><dd>{availabilityText(run.feed)}</dd></div>
      <div><dt>Fill policy</dt><dd>{availabilityText(run.fill_policy)}</dd></div>
      <div><dt>Session policy</dt><dd>{availabilityText(run.session_policy)}</dd></div>
      <div><dt>Cost scenario</dt><dd>{run.cost_policy.id}: {run.cost_policy.spread_bps} spread bps, {run.cost_policy.slippage_bps_per_fill} slippage bps per fill, {run.cost_policy.fee_per_share_per_fill} fee per share</dd></div>
      <div><dt>Cost evidence</dt><dd>{run.cost_policy.evidence}</dd></div>
      <div><dt>Accounting</dt><dd>{run.accounting.mode}; {run.accounting.coverage}; version: {availabilityText(run.accounting.version)}; unresolved: {run.accounting.unresolved.join(", ") || "none declared"}</dd></div>
      <div><dt>Evaluation</dt><dd>{run.provenance.evaluation}</dd></div>
      <div><dt>Code revision</dt><dd>{availabilityText(run.code.revision)}</dd></div>
      <div><dt>Source digest</dt><dd className="num">{availabilityText(run.code.source_sha256)}</dd></div>
      <div><dt>Working diff digest</dt><dd className="num">{availabilityText(run.code.working_diff_sha256)}</dd></div>
    </dl></section>
    <section className="card"><h2>Result</h2>
      {result ? <><p className="card-note">Python saved these metrics under its declared basis. Missing amounts remain unavailable.</p>
        <dl className="metric-grid">{Object.entries(result.metrics).map(([name, value]) =>
          <div key={name}><dt>{name.replaceAll("_", " ")}</dt><dd className="num">{metric(value)}</dd><small>{value.unit} · {value.basis}</small></div>)}</dl>
        <p className="card-note">Accounting coverage: {result.accounting.coverage}. Result ID: <span className="num">{result.id}</span>.</p>
        {result.limitations.length > 0 && <ul className="research-listing">{result.limitations.map((item) => <li key={item}>{item}</li>)}</ul>}
        <h3>Published artifacts</h3><ul className="artifact-list">{artifacts.map((artifact) => <li key={artifact.id}>
          <a href={`/api/demo/v1/runs/${status.run_id}/artifacts/${artifact.id}`}>{artifact.kind.replaceAll("_", " ")}</a>
          <span className="micro">{artifact.mime_type} · {artifact.byte_size} bytes · SHA-256 {artifact.sha256}</span>
        </li>)}</ul>
      </> : <p className="unavailable-note">{status.state === "completed" ? "Unavailable: this completed legacy job has no published result record." : "No result is published for this job."}</p>}
    </section>
  </main>;
}

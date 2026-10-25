import AvailableValue from "@/components/AvailableValue";
import Card from "@/components/Card";
import Disclosure from "@/components/Disclosure";
import StatTile from "@/components/StatTile";
import { artifactHref, availabilityText, getSavedDiagnostics, getSavedResult, type Artifact, type Availability } from "@/lib/demo";
import { formatTimestamp, labelFromKey } from "@/lib/format";
import { groupArtifactsByKind, headlineFigures, savedMetricGroups, untrackedCostComponents } from "@/lib/savedResult";
import { notFound } from "next/navigation";
import PageHeader from "@/components/PageHeader";
import ScopeNote from "@/components/ScopeNote";

function field(label: string, value: Availability<string>) {
  return <div><dt>{label}</dt><dd className="config-value">{availabilityText(value)}</dd></div>;
}

function countList(counts: Record<string, number>) {
  const entries = Object.entries(counts);
  return entries.length
    ? <dl className="audit-counts">{entries.map(([name, count]) => <div key={name}><dt>{labelFromKey(name)}</dt><dd className="num">{count}</dd></div>)}</dl>
    : <p className="card-note">The saved count map is present and empty.</p>;
}

function artifactList(resultId: string, artifacts: Artifact[]) {
  return artifacts.length ? <ul className="artifact-list">{artifacts.map((artifact) => <li key={artifact.id}>
    <a href={artifactHref(resultId, artifact.id)}>{labelFromKey(artifact.kind)}</a>
    <span className="note">{artifact.mime_type} · {artifact.byte_size} bytes · SHA-256 {artifact.sha256}</span>
  </li>)}</ul> : <p className="card-note">No indexed artifacts in this category.</p>;
}

export default async function SavedResultPage({ params }: { params: Promise<{ resultId: string }> }) {
  const { resultId } = await params;
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
  const artifactsByKind = groupArtifactsByKind(artifacts);
  const untrackedCosts = untrackedCostComponents(result.metrics);

  return <main>
    <PageHeader
      back={{ href: "/research", label: "Saved research" }}
      eyebrow={result.provenance.synthetic ? "Synthetic correctness" : result.provenance.retrospective ? "Retrospective" : "Saved-source result"}
      title={`${result.window.name} / ${result.variant}`}
      aside={<span className="micro">Saved result</span>}
    />
    <ScopeNote>{result.window.role} window, {formatTimestamp(result.window.start)} inclusive to {formatTimestamp(result.window.end_exclusive)} exclusive. {result.provenance.evaluation} evaluation; accounting coverage {result.accounting.coverage}.</ScopeNote>
    {warnings.map((warning) => <p className="research-warning" key={warning}>{warning}</p>)}

    <div className="stat-grid">{headlineFigures(result.metrics).map((figure) => <StatTile key={figure.label} {...figure} />)}</div>

    <Card title="Saved metrics" note="Values are displayed as supplied by the saved Python projection; this page does not recompute P&L.">
      {savedMetricGroups(result.metrics).map((group) => <div className="metric-group" key={group.title}>
        <h3>{group.title}</h3>{group.basis && <p className="card-note">{group.basis}</p>}
        <dl className="metric-grid">{group.rows.map((row) => <div key={row.name}><dt>{row.label}</dt><dd className="num"><AvailableValue {...row.value} /></dd>{row.ownBasis && <small>{row.ownBasis}</small>}</div>)}</dl>
      </div>)}
      {untrackedCosts.length > 0 && <Disclosure className="untracked-costs" summary={<>Not tracked in this result: {untrackedCosts.map((item) => item.label).join(", ")}. Shown as unavailable, never as zero.</>}>
        <ul className="research-listing">{untrackedCosts.map((item) => <li key={item.label}><strong>{item.label}</strong>: Unavailable. {item.reason}</li>)}</ul>
      </Disclosure>}
    </Card>

    <Card title="Accounting audit"><dl className="config-grid"><div><dt>Coverage</dt><dd>{result.accounting.coverage}</dd></div><div><dt>Mode</dt><dd>{result.accounting.mode}</dd></div><div><dt>Policy version</dt><dd>{availabilityText(result.accounting.version)}</dd></div></dl>
      {result.accounting.unresolved.length ? <ul className="research-listing">{result.accounting.unresolved.map((item) => <li key={item}>Unresolved accounting: {item}</li>)}</ul> : <p className="card-note">The saved result declares no unresolved accounting fields.</p>}
    </Card>

    <Card title="Limitations" note="Marked values use the saved marked basis and are distinct from realized results.">{result.limitations.length ? <ul className="research-listing">{result.limitations.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="card-note">No additional saved limitations were supplied.</p>}</Card>

    <Card title="Signal-quality audit" note="These are saved aggregate counts, not live signals and not counts recomputed by the browser.">
      {diagnostics.availability === "available" ? <div className="audit-columns"><div><h3>Execution and skip reasons</h3>{countList(diagnostics.value.signal_execution_reasons)}</div><div><h3>Candidate gate checks</h3>{countList(diagnostics.value.candidate_gate_checks)}</div></div> : <p className="unavailable-note">Unavailable: {diagnostics.detail}</p>}
      <p className="unavailable-note"><strong>Detailed filters unavailable.</strong> Filtering saved signals by ticker, direction, regime, gate decision or rejection reason isn&apos;t built yet.</p>
    </Card>

    <Card title="Saved data health"><dl className="config-grid">
      {field("Recorded feed", run.feed)}<div><dt>Saved symbols</dt><dd>{run.symbols.join(", ") || "Unavailable: no symbols were recorded."}</dd></div>
      {Object.entries(run.observed_bounds).map(([name, value]) => <div key={name}><dt>Saved observed {labelFromKey(name)}</dt><dd>{availabilityText(value)}</dd></div>)}
    </dl>{artifactsByKind.data.length ? <p className="card-note">Indexed data-health evidence is linked under Reproducibility. Its presence does not make fields available in this normalized view.</p> : <p className="unavailable-note">Unavailable: no indexed data-health or dataset-metadata artifact is linked to this result.</p>}
      <p className="unavailable-note"><strong>Source-specific health unavailable.</strong> Latest bar, stale fraction, missing sessions and calendar alignment aren&apos;t saved in a form this page can read yet, and it does not infer them.</p>
    </Card>

    <Card title="Shadow comparison"><p className="unavailable-note"><strong>Unavailable.</strong> A read-only baseline versus candidate comparison isn&apos;t built yet. No portfolio action is available here.</p></Card>

    <Disclosure className="card reproducibility" summary={<><h2>Reproducibility</h2><span className="micro">Configuration, hashes and source artifacts</span></>}>
      <p className="card-note">Result ID <span className="num">{result.id}</span>, saved run ID <span className="num">{run.id}</span>. The completed status refers to saved artifacts; it is not evidence that a job ran or that this configuration is approved.</p>
      <h3>Exact saved configuration</h3><dl className="config-grid">
        {field("Strategy version", run.strategy_version)} {field("Dataset SHA-256", run.dataset_sha256)}
        {field("Selected-data SHA-256", run.selected_data_sha256)} {field("Feed", run.feed)}
        {field("Fill policy", run.fill_policy)} {field("Session policy", run.session_policy)}
        {field("Revision", run.code.revision)} {field("Source SHA-256", run.code.source_sha256)}
        {field("Working diff SHA-256", run.code.working_diff_sha256)}
        <div><dt>Dataset ID</dt><dd className="config-value">{run.dataset_id}</dd></div>
        <div><dt>Selected window</dt><dd>{formatTimestamp(run.window.start)} inclusive to {formatTimestamp(run.window.end_exclusive)} exclusive ({run.window.role})</dd></div>
        {Object.entries(run.observed_bounds).map(([name, value]) => <div key={name}><dt>Observed {labelFromKey(name)}</dt><dd className="config-value">{availabilityText(value)}</dd></div>)}
        <div><dt>Symbols</dt><dd>{run.symbols.join(", ")}</dd></div><div><dt>Cost policy</dt><dd>{run.cost_policy.id}: {run.cost_policy.spread_bps} spread bps, {run.cost_policy.slippage_bps_per_fill} slippage bps/fill, {run.cost_policy.fee_per_share_per_fill} fee/share.</dd></div>
        <div><dt>Cost evidence</dt><dd>{run.cost_policy.evidence}</dd></div>
        <div><dt>Accounting</dt><dd>{run.accounting.mode}; {run.accounting.coverage}; {availabilityText(run.accounting.version)}</dd></div>
      </dl>
      <h3>Artifact inventory</h3><p className="card-note">Only allowlisted, result-scoped files are linked. An indexed file is evidence of availability, not proof that its contents were normalized above.</p><div className="artifact-groups">
        <div><h4>Accounting evidence</h4>{artifactList(result.id, artifactsByKind.accounting)}</div>
        <div><h4>Signal-quality evidence</h4>{artifactList(result.id, artifactsByKind.quality)}</div>
        <div><h4>Data-health evidence</h4>{artifactList(result.id, artifactsByKind.data)}</div>
        <div><h4>Reproducibility and results</h4>{artifactList(result.id, artifactsByKind.reproducibility)}</div>
      </div>{artifacts.length === 0 && <p className="unavailable-note">No safe, indexed artifacts are available for this saved result.</p>}
    </Disclosure>
  </main>;
}

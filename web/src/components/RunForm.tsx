"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { ReplayCatalog } from "@/lib/jobs";

const ERROR_TEXT: Record<string, string> = {
  dataset_changed: "The approved dataset changed on this host. Refresh the catalog before trying again.",
  dataset_unavailable: "The approved dataset is unavailable on this host.",
  idempotency_conflict: "This submission key was already used for different choices. Choose again and retry.",
  job_store_busy: "The local job store is busy. Retry with the same choices.",
  demo_unavailable: "The local demo service is unavailable. Check the dashboard process and retry.",
};

export default function RunForm({ catalog }: { catalog: ReplayCatalog }) {
  const router = useRouter();
  const datasets = catalog.datasets.filter((dataset) => dataset.available);
  const [datasetId, setDatasetId] = useState(datasets[0]?.id ?? "");
  const dataset = datasets.find((item) => item.id === datasetId);
  const [windowId, setWindowId] = useState(dataset?.windows[0]?.id ?? "");
  const [costId, setCostId] = useState(dataset?.cost_profile_ids[0] ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const key = useRef<string | null>(null);

  function resetKey() { key.current = null; setError(""); }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !dataset || !windowId || !costId) return;
    setBusy(true);
    setError("");
    key.current ??= crypto.randomUUID();
    try {
      const response = await fetch("/api/demo/v1/runs", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy_id: catalog.strategy.id, dataset_id: datasetId,
          window_id: windowId, cost_profile_id: costId, idempotency_key: key.current }),
      });
      const payload = await response.json();
      if (!response.ok) {
        const code = payload?.error?.code as string | undefined;
        if (code === "idempotency_conflict") key.current = null;
        setError(ERROR_TEXT[code ?? ""] ?? "The run request was rejected. Check the approved choices and retry.");
        return;
      }
      const runId = payload?.data?.status?.run_id;
      if (typeof runId !== "string") throw new Error("Missing run ID");
      router.push(`/runs/${encodeURIComponent(runId)}`);
    } catch {
      setError("The submission response could not be read. Retry to look up the same run.");
    } finally {
      setBusy(false);
    }
  }

  return <form className="card run-form" onSubmit={submit}>
    <h2>Approved historical replay</h2>
    <p className="card-note">The strategy is fixed. Choices below come from the local approved catalog. A worker must be running separately to complete a queued job.</p>
    <div className="run-fields">
      <div><label htmlFor="strategy">Strategy</label><input id="strategy" value={catalog.strategy.label} readOnly /></div>
      <div><label htmlFor="dataset">Dataset</label><select id="dataset" value={datasetId} disabled={!datasets.length || busy}
        onChange={(event) => { const next = datasets.find((item) => item.id === event.target.value); setDatasetId(event.target.value); setWindowId(next?.windows[0]?.id ?? ""); setCostId(next?.cost_profile_ids[0] ?? ""); resetKey(); }}>
        {datasets.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
      </select></div>
      <div><label htmlFor="window">Window</label><select id="window" value={windowId} disabled={!dataset || busy}
        onChange={(event) => { setWindowId(event.target.value); resetKey(); }}>
        {dataset?.windows.map((item) => <option key={item.id} value={item.id}>{item.id} · {item.start} to {item.end_exclusive}</option>)}
      </select></div>
      <div><label htmlFor="cost">Cost scenario</label><select id="cost" value={costId} disabled={!dataset || busy}
        onChange={(event) => { setCostId(event.target.value); resetKey(); }}>
        {catalog.cost_profiles.filter((item) => dataset?.cost_profile_ids.includes(item.id)).map((item) =>
          <option key={item.id} value={item.id}>{item.label}</option>) }
      </select></div>
    </div>
    {dataset && <p className="card-note">{dataset.synthetic ? "Synthetic correctness fixture" : "Retrospective market data"} · {dataset.feed} · SHA-256 {dataset.content_sha256}</p>}
    {!datasets.length && <p className="unavailable-note">No approved dataset is available on this host. Check local dataset files and metadata.</p>}
    {error && <p role="alert" className="research-warning">{error}</p>}
    <button className="button" type="submit" disabled={!dataset || busy}>{busy ? "Submitting…" : "Queue historical replay"}</button>
  </form>;
}

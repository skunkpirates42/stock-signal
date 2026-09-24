"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { JobStatus } from "@/lib/jobs";
import { startVisiblePolling } from "@/lib/polling";

export default function JobActions({ status }: { status: JobStatus }) {
  const router = useRouter();
  const active = ["queued", "running", "cancel_requested"].includes(status.state);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!active) return;
    return startVisiblePolling(async () => { router.refresh(); }, document, 3000);
  }, [active, router]);

  async function cancel() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/demo/v1/runs/${encodeURIComponent(status.run_id)}/cancel`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      });
      if (!response.ok) {
        const payload = await response.json();
        setError(payload?.error?.code === "job_store_busy" ? "The job store is busy. Try cancelling again." : "The cancel request failed. Try again.");
        return;
      }
      router.refresh();
    } catch { setError("The local demo service could not be reached. Try again."); }
    finally { setBusy(false); }
  }

  return <div className="run-actions">
    {active && <p className="micro" aria-live="polite">Status refreshes every 3 seconds.</p>}
    {(status.state === "queued" || status.state === "running") &&
      <button className="button" type="button" onClick={cancel} disabled={busy}>{busy ? "Cancelling…" : "Cancel run"}</button>}
    {error && <p role="alert" className="research-warning">{error}</p>}
  </div>;
}

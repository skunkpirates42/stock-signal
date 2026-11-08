"use client";

import { useState } from "react";
import { useRouteRefresh } from "@/hooks/useRouteRefresh";
import type { JobStatus } from "@/lib/jobs/contracts";
import { requestRunCancel } from "@/lib/runRequests";
import Button from "@/components/Button";

export default function JobActions({ status }: { status: JobStatus }) {
  const active = ["queued", "running", "cancel_requested"].includes(status.state);
  const refresh = useRouteRefresh(active ? 3000 : null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function cancel() {
    if (busy) return;
    setBusy(true);
    setError("");
    const outcome = await requestRunCancel(status.run_id);
    setBusy(false);
    if (outcome.ok) refresh();
    else setError(outcome.message);
  }

  return (
    <div className="run-actions">
      {active && (
        <p className="note" aria-live="polite">
          Status refreshes every 3 seconds.
        </p>
      )}
      {(status.state === "queued" || status.state === "running") && (
        <Button onClick={cancel} disabled={busy}>
          {busy ? "Cancelling…" : "Cancel run"}
        </Button>
      )}
      {error && (
        <p role="alert" className="research-warning">
          {error}
        </p>
      )}
    </div>
  );
}

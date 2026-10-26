"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { JobStatus } from "@/lib/jobs";
import { startVisiblePolling } from "@/lib/polling";
import { requestRunCancel } from "@/lib/runRequests";

export default function JobActions({ status }: { status: JobStatus }) {
  const router = useRouter();
  const active = ["queued", "running", "cancel_requested"].includes(status.state);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!active) return;
    return startVisiblePolling(
      async () => {
        router.refresh();
      },
      document,
      3000,
    );
  }, [active, router]);

  async function cancel() {
    if (busy) return;
    setBusy(true);
    setError("");
    const outcome = await requestRunCancel(status.run_id);
    setBusy(false);
    if (outcome.ok) router.refresh();
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
        <button className="button" type="button" onClick={cancel} disabled={busy}>
          {busy ? "Cancelling…" : "Cancel run"}
        </button>
      )}
      {error && (
        <p role="alert" className="research-warning">
          {error}
        </p>
      )}
    </div>
  );
}

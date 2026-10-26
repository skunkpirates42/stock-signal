export interface ReplayChoices {
  strategy_id: string;
  dataset_id: string;
  window_id: string;
  cost_profile_id: string;
  idempotency_key: string;
}

export type QueueOutcome =
  { ok: true; runId: string } | { ok: false; message: string; keyRejected: boolean };

export type CancelOutcome = { ok: true } | { ok: false; message: string };

const QUEUE_ERROR_TEXT: Record<string, string> = {
  dataset_changed:
    "The approved dataset changed on this host. Refresh the catalog before trying again.",
  dataset_unavailable: "The approved dataset is unavailable on this host.",
  idempotency_conflict:
    "This submission key was already used for different choices. Choose again and retry.",
  job_store_busy: "The local job store is busy. Retry with the same choices.",
  demo_unavailable: "The local demo service is unavailable. Check the dashboard process and retry.",
};

function errorCode(payload: unknown): string | undefined {
  const code = (payload as { error?: { code?: unknown } } | null)?.error?.code;
  return typeof code === "string" ? code : undefined;
}

export async function queueReplayRun(choices: ReplayChoices): Promise<QueueOutcome> {
  try {
    const response = await fetch("/api/demo/v1/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(choices),
    });
    const payload = await response.json();
    if (!response.ok) {
      const code = errorCode(payload);
      return {
        ok: false,
        message:
          QUEUE_ERROR_TEXT[code ?? ""] ??
          "The run request was rejected. Check the approved choices and retry.",
        keyRejected: code === "idempotency_conflict",
      };
    }
    const runId = payload?.data?.status?.run_id;
    if (typeof runId !== "string") throw new Error("Missing run ID");
    return { ok: true, runId };
  } catch {
    return {
      ok: false,
      message: "The submission response could not be read. Retry to look up the same run.",
      keyRejected: false,
    };
  }
}

export async function requestRunCancel(runId: string): Promise<CancelOutcome> {
  try {
    const response = await fetch(`/api/demo/v1/runs/${encodeURIComponent(runId)}/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    if (response.ok) return { ok: true };
    const payload = await response.json();
    return {
      ok: false,
      message:
        errorCode(payload) === "job_store_busy"
          ? "The job store is busy. Try cancelling again."
          : "The cancel request failed. Try again.",
    };
  } catch {
    return { ok: false, message: "The local demo service could not be reached. Try again." };
  }
}

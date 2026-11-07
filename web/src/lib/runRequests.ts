import { isOpaqueDemoId } from "@/lib/demo/contracts";
import { readFields, readString, ResponseShapeError, type Read } from "@/lib/parse";

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

export const RUN_REQUEST_TIMEOUT_MS = 35_000;

const QUEUE_ERROR_TEXT: Record<string, string> = {
  dataset_changed:
    "The approved dataset changed on this host. Refresh the catalog before trying again.",
  dataset_unavailable: "The approved dataset is unavailable on this host.",
  idempotency_conflict:
    "This submission key was already used for different choices. Choose again and retry.",
  job_store_busy: "The local job store is busy. Retry with the same choices.",
  demo_unavailable: "The local demo service is unavailable. Check the dashboard process and retry.",
};

const readMutationRunId: Read<string> = (value, path) => {
  const dataField = readFields(value, path)("data", readFields);
  const statusField = dataField("status", readFields);
  const runId = statusField("run_id", readString);
  if (!isOpaqueDemoId(runId))
    throw new ResponseShapeError(`${path}.data.status.run_id`, "opaque run ID");
  return runId;
};

const readMutationErrorCode: Read<string> = (value, path) => {
  const errorField = readFields(value, path)("error", readFields);
  return errorField("code", readString);
};

class RunRequestTimeout extends Error {}

async function postRunMutation<T>(
  path: string,
  body: object,
  readOutcome: (response: Response) => Promise<T>,
): Promise<T> {
  const controller = new AbortController();
  let timeout: ReturnType<typeof setTimeout> | undefined;
  const deadline = new Promise<never>((_, reject) => {
    timeout = setTimeout(() => {
      reject(new RunRequestTimeout());
      controller.abort();
    }, RUN_REQUEST_TIMEOUT_MS);
  });
  try {
    const fetchOutcome = async () => {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      return readOutcome(response);
    };
    return await Promise.race([fetchOutcome(), deadline]);
  } finally {
    clearTimeout(timeout);
  }
}

async function readQueueOutcome(response: Response): Promise<QueueOutcome> {
  if (response.ok) {
    return { ok: true, runId: readMutationRunId(await response.json(), "submission") };
  }
  const code = readMutationErrorCode(await response.json(), "submission");
  return {
    ok: false,
    message: Object.hasOwn(QUEUE_ERROR_TEXT, code)
      ? QUEUE_ERROR_TEXT[code]
      : "The run request was rejected. Check the approved choices and retry.",
    keyRejected: code === "idempotency_conflict",
  };
}

async function readCancelOutcome(response: Response, runId: string): Promise<CancelOutcome> {
  if (response.ok) {
    const confirmedRunId = readMutationRunId(await response.json(), "cancellation");
    if (confirmedRunId !== runId)
      throw new ResponseShapeError("cancellation.data.status.run_id", "requested run ID");
    return { ok: true };
  }
  const code = readMutationErrorCode(await response.json(), "cancellation");
  return {
    ok: false,
    message:
      code === "job_store_busy"
        ? "The job store is busy. Try cancelling again."
        : "The cancel request failed. Try again.",
  };
}

export async function queueReplayRun(choices: ReplayChoices): Promise<QueueOutcome> {
  try {
    return await postRunMutation("/api/demo/v1/runs", choices, readQueueOutcome);
  } catch (error) {
    let message = "The submission response could not be read. Retry to look up the same run.";
    if (error instanceof RunRequestTimeout) {
      message =
        "The submission timed out. The run may still have been queued. Retry to look up the same run.";
    } else if (!(error instanceof SyntaxError || error instanceof ResponseShapeError)) {
      message =
        "The local demo service could not be reached. The run may still have been queued. Retry to look up the same run.";
    }
    return {
      ok: false,
      message,
      keyRejected: false,
    };
  }
}

export async function requestRunCancel(runId: string): Promise<CancelOutcome> {
  if (!isOpaqueDemoId(runId))
    return {
      ok: false,
      message: "This run ID is invalid. Refresh the run list before cancelling.",
    };
  try {
    return await postRunMutation(
      `/api/demo/v1/runs/${encodeURIComponent(runId)}/cancel`,
      {},
      (response) => readCancelOutcome(response, runId),
    );
  } catch (error) {
    if (error instanceof RunRequestTimeout)
      return {
        ok: false,
        message: "The cancel request timed out. Check the run status before trying again.",
      };
    if (error instanceof SyntaxError || error instanceof ResponseShapeError)
      return {
        ok: false,
        message:
          "The cancellation response could not be read. Check the run status before trying again.",
      };
    return { ok: false, message: "The local demo service could not be reached. Try again." };
  }
}

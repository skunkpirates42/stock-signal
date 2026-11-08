import { polledResourceName, recordFailure, RequestFailure } from "@/lib/failures";
import type { Read } from "@/lib/parse";
import { startVisiblePolling } from "@/lib/polling";

export interface PolledResource<T> {
  data: T | null;
  failed: boolean;
  checkedAt: Date | null;
}

export const NOT_YET_POLLED: PolledResource<never> = { data: null, failed: false, checkedAt: null };

export const POLL_REQUEST_TIMEOUT_MS = 10_000;

async function fetchParsed<T>(url: string, read: Read<T>, signal: AbortSignal): Promise<T> {
  const controller = new AbortController();
  let rejectAborted: (reason: unknown) => void = () => {};
  const aborted = new Promise<never>((_, reject) => {
    rejectAborted = reject;
  });
  const abort = () => {
    rejectAborted(new RequestFailure("aborted"));
    controller.abort();
  };
  signal.addEventListener("abort", abort, { once: true });
  const timeout = setTimeout(() => {
    rejectAborted(new RequestFailure("timeout"));
    controller.abort();
  }, POLL_REQUEST_TIMEOUT_MS);
  const fetchData = async () => {
    let response: Response;
    try {
      response = await fetch(url, { cache: "no-store", signal: controller.signal });
    } catch {
      throw new RequestFailure("transport");
    }
    if (!response.ok) throw new RequestFailure("http");
    return read(await response.json(), url);
  };
  try {
    if (signal.aborted) abort();
    return await Promise.race([fetchData(), aborted]);
  } finally {
    clearTimeout(timeout);
    signal.removeEventListener("abort", abort);
  }
}

// A failed poll keeps the last good data so views can show it as possibly stale.
export function startPolledResource<T>(
  url: string,
  read: Read<T>,
  onChange: (next: PolledResource<T>) => void,
  doc: Parameters<typeof startVisiblePolling>[1],
  intervalMs: number,
) {
  let active = true;
  let current: PolledResource<T> = NOT_YET_POLLED;
  const controller = new AbortController();
  const publish = (next: PolledResource<T>) => {
    if (!active) return;
    current = next;
    onChange(next);
  };
  const stopPolling = startVisiblePolling(
    async () => {
      try {
        const data = await fetchParsed(url, read, controller.signal);
        publish({ data, failed: false, checkedAt: new Date() });
      } catch (error) {
        if (!active) return;
        recordFailure(polledResourceName(url), error);
        publish({ data: current.data, failed: true, checkedAt: new Date() });
      }
    },
    doc,
    intervalMs,
  );
  return () => {
    active = false;
    controller.abort();
    stopPolling();
  };
}

export function newerOf(clock: Date, checkedAt: Date | null): Date {
  return checkedAt && checkedAt > clock ? checkedAt : clock;
}

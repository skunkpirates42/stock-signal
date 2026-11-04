import type { Read } from "@/lib/parse";
import { startVisiblePolling } from "@/lib/polling";

export interface PolledResource<T> {
  data: T | null;
  failed: boolean;
  checkedAt: Date | null;
}

export const NOT_YET_POLLED: PolledResource<never> = { data: null, failed: false, checkedAt: null };

const REQUEST_TIMEOUT_MS = 10_000;

async function fetchParsed<T>(url: string, read: Read<T>, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, {
    cache: "no-store",
    signal: AbortSignal.any([signal, AbortSignal.timeout(REQUEST_TIMEOUT_MS)]),
  });
  if (!response.ok) throw new Error(`${url} responded ${response.status}`);
  return read(await response.json(), url);
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
      } catch {
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

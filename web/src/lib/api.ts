import { readMetrics, readSignal, readSignalSearchResult, readTrade } from "@/lib/types";
import { signalQueryParams, type SignalQuery } from "@/lib/signalSearch";
import { dateRangeQuery, type DateRange } from "@/lib/dateRange";
import { readArrayOf, type Read } from "@/lib/parse";

export const API_BASE = process.env.FLASK_API_URL ?? "http://127.0.0.1:8000";
export const READ_TIMEOUT_MS = 10_000;

async function get<T>(path: string, read: Read<T>): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(READ_TIMEOUT_MS),
  });
  if (!response.ok) {
    throw new Error(`${path} responded ${response.status}`);
  }
  return read(await response.json(), path);
}

export function getMetrics(source?: string, range: DateRange = {}) {
  const params = dateRangeQuery(range);
  if (source) params.set("source", source);
  const query = params.size ? `?${params}` : "";
  return get(`/api/metrics${query}`, readMetrics);
}

export function getSignals(opts: { source?: string; limit?: number } = {}) {
  const params = new URLSearchParams();
  if (opts.source) params.set("source", opts.source);
  params.set("limit", String(opts.limit ?? 500));
  return get(`/api/signals?${params}`, readArrayOf(readSignal));
}

export function searchSignals(query: SignalQuery) {
  return get(`/api/signals/search?${signalQueryParams(query)}`, readSignalSearchResult);
}

export function getTrades(opts: { source?: string; limit?: number } = {}) {
  const params = new URLSearchParams();
  if (opts.source) params.set("source", opts.source);
  params.set("limit", String(opts.limit ?? 500));
  return get(`/api/trades?${params}`, readArrayOf(readTrade));
}

export function getOpenPositions(source = "live") {
  return get(`/api/open?source=${encodeURIComponent(source)}`, readArrayOf(readTrade));
}

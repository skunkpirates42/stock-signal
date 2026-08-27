import type { Metrics, Signal, Trade } from "@/lib/types";

const BASE = process.env.FLASK_API_URL ?? "http://127.0.0.1:8000";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${path} responded ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getMetrics(source?: string) {
  const query = source ? `?source=${source}` : "";
  return get<Metrics>(`/api/metrics${query}`);
}

export function getSignals(opts: { source?: string; limit?: number } = {}) {
  const params = new URLSearchParams();
  if (opts.source) params.set("source", opts.source);
  params.set("limit", String(opts.limit ?? 500));
  return get<Signal[]>(`/api/signals?${params}`);
}

export function getTrades(opts: { source?: string; limit?: number } = {}) {
  const params = new URLSearchParams();
  if (opts.source) params.set("source", opts.source);
  params.set("limit", String(opts.limit ?? 500));
  return get<Trade[]>(`/api/trades?${params}`);
}

export function getOpenPositions() {
  return get<Trade[]>("/api/open");
}

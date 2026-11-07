import { closedDateRange } from "@/lib/dateRange";
import type { SignalCriteria } from "@/lib/filters";

export interface SignalQuery extends SignalCriteria {
  source: "live" | "all";
  page: number;
  snapshotId?: number;
}

export type SignalSearchParams = Record<string, string | string[] | undefined>;

function singleParam(params: SignalSearchParams, name: string): string | undefined {
  const value = params[name];
  if (Array.isArray(value)) throw new Error(`Use only one ${name} parameter.`);
  return value;
}

function integerParam(raw: string | undefined, name: string, minimum: number): number | undefined {
  if (raw === undefined) return undefined;
  const value = Number(raw);
  if (!/^\d+$/.test(raw) || !Number.isSafeInteger(value) || value < minimum) {
    throw new Error(`${name} must be an integer of at least ${minimum}.`);
  }
  return value;
}

export function parseSignalQuery(params: SignalSearchParams): SignalQuery {
  const source = singleParam(params, "source") ?? "live";
  if (source !== "live" && source !== "all") throw new Error("Source must be live or all.");
  const direction = singleParam(params, "direction") || undefined;
  if (
    direction !== undefined &&
    direction !== "LONG" &&
    direction !== "SHORT" &&
    direction !== "WAIT"
  ) {
    throw new Error("Direction must be LONG, SHORT or WAIT.");
  }
  const rawConfidence = singleParam(params, "min_confidence");
  const minConfidence = rawConfidence === undefined ? 0 : Number(rawConfidence);
  if (
    !Number.isFinite(minConfidence) ||
    minConfidence < 0 ||
    minConfidence > 1 ||
    rawConfidence === ""
  ) {
    throw new Error("Minimum confidence must be between 0 and 1.");
  }
  const includeWait = singleParam(params, "include_wait") ?? "false";
  if (includeWait !== "true" && includeWait !== "false") {
    throw new Error("Include WAIT must be true or false.");
  }
  const from = singleParam(params, "from") || undefined;
  const to = singleParam(params, "to") || undefined;
  const range = closedDateRange({ from, to });
  if (range.from !== from || range.to !== to) throw new Error("Dates must use YYYY-MM-DD.");
  if (from && to && from > to) throw new Error("From must be on or before To.");
  const ticker = singleParam(params, "ticker")?.trim().toUpperCase() || undefined;
  if (ticker && ticker.length > 32) throw new Error("Ticker must be at most 32 characters.");
  const page = integerParam(singleParam(params, "page"), "Page", 1) ?? 1;
  if (page > 2_147_483_647) throw new Error("Page is too large.");
  return {
    source,
    ticker,
    direction,
    minConfidence,
    hideWait: includeWait !== "true",
    from,
    to,
    page,
    snapshotId: integerParam(singleParam(params, "snapshot_id"), "Snapshot", 0),
  };
}

export function signalQueryParams(query: SignalQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (query.source === "all") params.set("source", "all");
  if (query.ticker) params.set("ticker", query.ticker);
  if (query.direction) params.set("direction", query.direction);
  if (query.minConfidence) params.set("min_confidence", String(query.minConfidence));
  if (!query.hideWait) params.set("include_wait", "true");
  if (query.from) params.set("from", query.from);
  if (query.to) params.set("to", query.to);
  if (query.page > 1) params.set("page", String(query.page));
  if (query.snapshotId !== undefined) params.set("snapshot_id", String(query.snapshotId));
  return params;
}

export function signalSearchHref(query: SignalQuery): string {
  const params = signalQueryParams(query);
  return params.size ? `/signals?${params}` : "/signals";
}

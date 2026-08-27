import type { Vote, VoteRow } from "@/lib/types";

const ORDER = [
  "rsi", "price_vs_sma20", "sma20_vs_sma50", "price_vs_vwap", "macd", "bb",
] as const;

const LABELS: Record<string, string> = {
  rsi: "RSI (14)",
  price_vs_sma20: "Price vs SMA20",
  sma20_vs_sma50: "SMA20 vs SMA50",
  price_vs_vwap: "Price vs VWAP",
  macd: "MACD",
  bb: "BB %B",
};

function detailFor(indicator: string, values: Record<string, number>): string {
  const n = (key: string, digits = 2) =>
    values[key] === undefined ? "—" : values[key].toFixed(digits);
  switch (indicator) {
    case "rsi": return `${n("rsi")}  (bull <45, bear >55)`;
    case "price_vs_sma20": return `${n("close")} vs ${n("sma20")}`;
    case "sma20_vs_sma50": return `${n("sma20")} vs ${n("sma50")}`;
    case "price_vs_vwap": return `${n("close")} vs ${n("vwap")}`;
    case "macd": return n("macd", 3);
    case "bb": return `${n("bb_pct", 3)}  (bull <0.20, bear >0.80)`;
    default: return "";
  }
}

export function parseIndicators(json: string | null | undefined): VoteRow[] {
  if (!json) return [];
  let parsed: { votes?: Record<string, Vote>; values?: Record<string, number> };
  try {
    parsed = JSON.parse(json);
  } catch {
    return [];
  }
  const votes = parsed.votes;
  if (!votes) return [];
  const values = parsed.values ?? {};
  return ORDER.filter((key) => key in votes).map((key) => ({
    indicator: key,
    label: LABELS[key] ?? key,
    vote: votes[key],
    detail: detailFor(key, values),
  }));
}

export function voteTally(rows: VoteRow[]) {
  return {
    bull: rows.filter((r) => r.vote === "bull").length,
    bear: rows.filter((r) => r.vote === "bear").length,
    neutral: rows.filter((r) => r.vote === "neutral").length,
  };
}

import type { Direction, Vote, VoteRow } from "@/lib/types";

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

const STOP_ATR_MULTIPLIER = 1.5;
const TARGET_ATR_MULTIPLIER = 3.0;

interface ParsedSignalJson {
  votes: unknown;
  values: Record<string, unknown>;
}

function parseSignalJson(json: string | null | undefined): ParsedSignalJson | null {
  if (!json) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    return null;
  }
  if (parsed === null || typeof parsed !== "object") return null;
  const obj = parsed as { votes?: unknown; values?: unknown };
  const values =
    obj.values && typeof obj.values === "object" ? (obj.values as Record<string, unknown>) : {};
  return { votes: obj.votes, values };
}

function numericValue(values: Record<string, unknown>, key: string): number | null {
  const v = values[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function detailFor(indicator: string, values: Record<string, unknown>): string {
  const n = (key: string, digits = 2) => {
    const v = numericValue(values, key);
    return v === null ? "—" : v.toFixed(digits);
  };
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
  const parsed = parseSignalJson(json);
  if (!parsed) return [];
  const votes = parsed.votes;
  if (!votes || typeof votes !== "object") return [];
  const voteMap = votes as Record<string, Vote>;
  return ORDER.filter((key) => key in voteMap).map((key) => ({
    indicator: key,
    label: LABELS[key] ?? key,
    vote: voteMap[key],
    detail: detailFor(key, parsed.values),
  }));
}

export function voteTally(rows: VoteRow[]) {
  return {
    bull: rows.filter((r) => r.vote === "bull").length,
    bear: rows.filter((r) => r.vote === "bear").length,
    neutral: rows.filter((r) => r.vote === "neutral").length,
  };
}

export function parseAtr(json: string | null | undefined): number | null {
  const parsed = parseSignalJson(json);
  return parsed ? numericValue(parsed.values, "atr") : null;
}

export type LevelDirection = Exclude<Direction, "WAIT">;

export interface AtrArithmetic {
  atr: number;
  stopMultiplier: number;
  targetMultiplier: number;
  stopOperator: "+" | "-";
  targetOperator: "+" | "-";
}

// Mirrors the Python engine: stop = entry -/+ (ATR * 1.5), target = entry +/- (ATR * 3.0),
// with the sign flipped between LONG and SHORT.
export function atrArithmetic(direction: LevelDirection, atr: number): AtrArithmetic {
  return {
    atr,
    stopMultiplier: STOP_ATR_MULTIPLIER,
    targetMultiplier: TARGET_ATR_MULTIPLIER,
    stopOperator: direction === "LONG" ? "-" : "+",
    targetOperator: direction === "LONG" ? "+" : "-",
  };
}

import type { EquityPoint } from "@/lib/types";
import { formatBalance, formatTimestamp } from "@/lib/format";

export function summarizeEquityCurve(points: EquityPoint[]): string {
  const first = points[0];
  const last = points[points.length - 1];
  const values = points.map((point) => point.equity);
  return (
    `Equity went from ${formatBalance(first.equity)} at ${formatTimestamp(first.label)} ` +
    `to ${formatBalance(last.equity)} at ${formatTimestamp(last.label)}, ` +
    `with a low of ${formatBalance(Math.min(...values))} and a high of ${formatBalance(Math.max(...values))} ` +
    `across ${points.length} points.`
  );
}

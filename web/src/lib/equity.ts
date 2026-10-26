import type { EquityPoint } from "@/lib/types";
import { formatPrice, formatTimestamp } from "@/lib/format";

export function summarizeEquityCurve(points: EquityPoint[]): string {
  const first = points[0];
  const last = points[points.length - 1];
  const values = points.map((point) => point.equity);
  return (
    `Equity went from ${formatPrice(first.equity)} at ${formatTimestamp(first.label)} ` +
    `to ${formatPrice(last.equity)} at ${formatTimestamp(last.label)}, ` +
    `with a low of ${formatPrice(Math.min(...values))} and a high of ${formatPrice(Math.max(...values))} ` +
    `across ${points.length} points.`
  );
}

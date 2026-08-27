import type { Breakdown } from "@/lib/types";
import { shareOfMax } from "@/lib/scale";

export interface BreakdownRow extends Breakdown {
  name: string;
  share: number;
}

export function breakdownRows(rows: Record<string, Breakdown>): BreakdownRow[] {
  const entries = Object.entries(rows);
  const shares = shareOfMax(entries.map(([, breakdown]) => breakdown.pnl));
  return entries
    .map(([name, breakdown], index) => ({ ...breakdown, name, share: shares[index] }))
    .sort((a, b) => b.pnl - a.pnl);
}

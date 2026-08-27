import type { Trade } from "@/lib/types";

export interface Distance {
  dollars: number;
  percent: number;
}

const STALE_AFTER_MS = 24 * 60 * 60 * 1000;

// As-of-entry only: how far price had to move from the entry price to hit the stop or
// target. This says nothing about where price is now — there is no quote feed behind
// this dashboard to know that.
export function distanceToStop(trade: Pick<Trade, "direction" | "entry" | "stop">): Distance {
  const dollars = trade.direction === "SHORT" ? trade.stop - trade.entry : trade.entry - trade.stop;
  return { dollars, percent: trade.entry === 0 ? 0 : dollars / trade.entry };
}

export function distanceToTarget(trade: Pick<Trade, "direction" | "entry" | "target">): Distance {
  const dollars = trade.direction === "SHORT" ? trade.entry - trade.target : trade.target - trade.entry;
  return { dollars, percent: trade.entry === 0 ? 0 : dollars / trade.entry };
}

export function isStale(openedAt: string, now: Date): boolean {
  return now.getTime() - new Date(openedAt).getTime() > STALE_AFTER_MS;
}

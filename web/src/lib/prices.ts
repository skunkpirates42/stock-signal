import type { Trade } from "@/lib/types";

export interface PriceMark {
  price: number;
  timestamp: string;
}
export interface PositionPrices {
  feed: "iex";
  checked_at: string;
  prices: Record<string, PriceMark>;
}

export function priceIsStale(mark: PriceMark, now: Date): boolean {
  const age = now.getTime() - Date.parse(mark.timestamp);
  return !Number.isFinite(age) || age < 0 || age > 60_000;
}

export function markedPosition(trade: Trade, price: number) {
  const sign = trade.direction === "SHORT" ? -1 : 1;
  return {
    pnl: (price - trade.entry) * sign * (trade.remaining_shares ?? trade.shares),
    toStop: (price - trade.stop) * sign,
    toTarget: (trade.target - price) * sign,
  };
}

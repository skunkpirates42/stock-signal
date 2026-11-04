import {
  readFields,
  readLiteral,
  readNumber,
  readRecordOf,
  readString,
  ResponseShapeError,
  type Read,
} from "@/lib/parse";
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

const readPriceMark: Read<PriceMark> = (value, path) => {
  const field = readFields(value, path);
  const price = field("price", readNumber);
  if (price <= 0) throw new ResponseShapeError(`${path}.price`, "positive price");
  return { price, timestamp: field("timestamp", readString) };
};

export const readPositionPrices: Read<PositionPrices> = (value, path) => {
  const field = readFields(value, path);
  return {
    feed: field("feed", readLiteral("iex")),
    checked_at: field("checked_at", readString),
    prices: field("prices", readRecordOf(readPriceMark)),
  };
};

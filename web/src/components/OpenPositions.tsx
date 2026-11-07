"use client";

import { usePolledResource } from "@/hooks/usePolledResource";
import { readPositionPrices } from "@/lib/prices";
import type { Trade } from "@/lib/types";
import { isStale } from "@/lib/positions";
import { newerOf } from "@/lib/polledResource";
import PositionCard from "@/components/PositionCard";

export interface OpenPositionsProps {
  positions: Trade[];
  now: Date;
}

export default function OpenPositions({ positions, now }: OpenPositionsProps) {
  const hasLive = positions.some((position) => position.source === "live");
  const {
    data: prices,
    failed,
    checkedAt,
  } = usePolledResource(hasLive ? "/api/position-prices" : null, readPositionPrices, 5000);
  return (
    <section className="open-positions stack">
      <h2 className="micro">Open positions</h2>
      <p className="positions-note">
        Live positions use the latest IEX trade, refreshed while visible with five seconds between
        requests. Estimated unrealized P&amp;L excludes fees and is not a guaranteed exit value.
        Historical and unknown-source positions show distances as of entry.
      </p>
      {hasLive && failed && (
        <p className="micro" role="status">
          Price service unavailable. Last received prices may be stale.
        </p>
      )}
      {positions.length === 0 ? (
        <p className="positions-empty">No open positions.</p>
      ) : (
        <div className="position-grid">
          {positions.map((position) => (
            <PositionCard
              key={position.id}
              position={position}
              mark={position.source === "live" ? prices?.prices[position.ticker] : undefined}
              now={newerOf(now, checkedAt)}
              priceFailed={failed}
              stale={isStale(position.entry_at ?? position.created_at, now)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

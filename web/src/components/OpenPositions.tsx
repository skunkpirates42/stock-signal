"use client";

import { useEffect, useState } from "react";
import { startVisiblePolling } from "@/lib/polling";
import type { PositionPrices } from "@/lib/prices";
import type { Trade } from "@/lib/types";
import { isStale } from "@/lib/positions";
import PositionCard from "@/components/PositionCard";

export interface OpenPositionsProps {
  positions: Trade[];
  now: Date;
}

export default function OpenPositions({ positions, now }: OpenPositionsProps) {
  const [prices, setPrices] = useState<PositionPrices | null>(null);
  const [failed, setFailed] = useState(false);
  const [checkedAt, setCheckedAt] = useState(now);
  const hasLive = positions.some((position) => position.source === "live");
  useEffect(() => {
    if (!hasLive) return;
    let active = true;
    const controller = new AbortController();
    const stop = startVisiblePolling(
      async () => {
        try {
          const response = await fetch("/api/position-prices", {
            cache: "no-store",
            signal: AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]),
          });
          if (!response.ok) throw new Error("Prices unavailable");
          const data: PositionPrices = await response.json();
          if (active) {
            setPrices(data);
            setFailed(false);
          }
        } catch {
          if (active) setFailed(true);
        } finally {
          if (active) setCheckedAt(new Date());
        }
      },
      document,
      5000,
    );
    return () => {
      active = false;
      controller.abort();
      stop();
    };
  }, [hasLive]);
  return (
    <section className="open-positions">
      <h2 className="micro">Open positions</h2>
      <p className="positions-note">
        Live positions use the latest IEX trade, checked every five seconds while visible. Estimated
        unrealized P&amp;L excludes fees and is not a guaranteed exit value. Historical and
        unknown-source positions show distances as of entry.
      </p>
      {hasLive && (
        <p className="micro" role="status">
          {failed
            ? "Price service unavailable. Last received prices may be stale."
            : prices?.market_open === false
              ? "Regular market closed · showing last available trades."
              : prices?.market_open === true
                ? "Regular market open · IEX"
                : "Market status unavailable"}
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
              now={checkedAt}
              priceFailed={failed}
              stale={isStale(position.entry_at ?? position.created_at, now)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

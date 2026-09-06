import type { Trade } from "@/lib/types";
import { isStale } from "@/lib/positions";
import PositionCard from "@/components/PositionCard";

export interface OpenPositionsProps {
  positions: Trade[];
  now: Date;
}

export default function OpenPositions({ positions, now }: OpenPositionsProps) {
  return (
    <section className="open-positions">
      <h2 className="micro">Open positions</h2>
      <p className="positions-note">
        No live price feed is wired into this dashboard. The columns below show distance to
        stop and distance to target as of entry — not current value or unrealized P&amp;L,
        which this app has no data to compute.
      </p>
      {positions.length === 0 ? (
        <p className="positions-empty">No open positions.</p>
      ) : (
        <div className="position-grid">
          {positions.map((position) => (
            <PositionCard
              key={position.id}
              position={position}
              stale={isStale(position.entry_at ?? position.created_at, now)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

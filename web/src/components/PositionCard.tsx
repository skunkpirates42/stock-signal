import type { Trade } from "@/lib/types";
import { formatCurrency, formatTimestamp } from "@/lib/format";
import { distanceToStop, distanceToTarget } from "@/lib/positions";
import LevelScale from "@/components/LevelScale";

export interface PositionCardProps {
  position: Trade;
  stale: boolean;
}

export default function PositionCard({ position, stale }: PositionCardProps) {
  const toStop = distanceToStop(position);
  const toTarget = distanceToTarget(position);

  return (
    <article className="card position-card">
      <header className="position-card-head">
        <span className="position-card-ticker num">{position.ticker}</span>
        <span className={`signal-badge tone-${position.direction === "SHORT" ? "negative" : "positive"}`}>
          {position.direction}
        </span>
        {stale && <span className="positions-stale-badge">STALE</span>}
        <span className="micro position-card-age">{formatTimestamp(position.created_at)}</span>
      </header>

      <LevelScale
        stop={position.stop}
        entry={position.entry}
        target={position.target}
        direction={position.direction}
      />

      <dl className="pair-grid">
        <div>
          <dt className="micro">To stop</dt>
          <dd className="num tone-negative">{formatCurrency(toStop.dollars)}</dd>
        </div>
        <div>
          <dt className="micro">To target</dt>
          <dd className="num tone-positive">{formatCurrency(toTarget.dollars)}</dd>
        </div>
        <div>
          <dt className="micro">Shares</dt>
          <dd className="num">{position.shares}</dd>
        </div>
      </dl>
    </article>
  );
}

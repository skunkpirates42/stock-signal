import type { Trade } from "@/lib/types";
import { provenance } from "@/lib/execution";
import { formatCurrency, formatPrice, formatTimestamp } from "@/lib/format";
import { distanceToStop, distanceToTarget } from "@/lib/positions";
import { markedPosition, priceIsStale, type PriceMark } from "@/lib/prices";
import LevelScale from "@/components/LevelScale";

export interface PositionCardProps {
  position: Trade;
  stale: boolean;
  mark?: PriceMark;
  now?: Date;
  priceFailed?: boolean;
}

export default function PositionCard({
  position,
  stale,
  mark,
  now = new Date(),
  priceFailed = false,
}: PositionCardProps) {
  const marked = mark ? markedPosition(position, mark.price) : null;
  const stalePrice = mark && (priceFailed || priceIsStale(mark, now));
  const toStop = distanceToStop(position);
  const toTarget = distanceToTarget(position);

  return (
    <article className="card position-card">
      <header className="position-card-head">
        <span className="position-card-ticker num">{position.ticker}</span>
        <span
          className={`signal-badge tone-${position.direction === "SHORT" ? "negative" : "positive"}`}
        >
          {position.direction}
        </span>
        {stale && <span className="positions-stale-badge">POSITION AGE &gt; 24H</span>}
        <span className="micro position-card-age">
          {formatTimestamp(position.entry_at ?? position.created_at)}
        </span>
      </header>

      <p className="micro">
        {provenance(position)} · {position.source ?? "unknown source"} ·{" "}
        {position.backend ?? "unknown backend"} · {position.account ?? "unknown account"}
      </p>
      <LevelScale
        stop={position.stop}
        entry={position.entry}
        target={position.target}
        direction={position.direction}
        current={mark?.price}
      />

      {position.source === "live" && (
        <p className="micro">
          {mark ? (
            <>
              IEX last trade · {formatTimestamp(mark.timestamp)}
              {stalePrice ? " · STALE PRICE" : ""}
            </>
          ) : (
            "Price unavailable"
          )}
        </p>
      )}
      <dl className="pair-grid">
        {position.source === "live" && (
          <>
            <div>
              <dt className="micro">Last price</dt>
              <dd className="num">{mark ? formatPrice(mark.price) : "—"}</dd>
            </div>
            <div>
              <dt className="micro">Est. unrealized P&amp;L{stalePrice ? " (stale)" : ""}</dt>
              <dd className="num">{marked ? formatCurrency(marked.pnl) : "—"}</dd>
            </div>
          </>
        )}
        <div>
          <dt className="micro">To stop{mark ? " (last price)" : " (at entry)"}</dt>
          <dd className="num">{formatCurrency(marked?.toStop ?? toStop.dollars)}</dd>
        </div>
        <div>
          <dt className="micro">To target{mark ? " (last price)" : " (at entry)"}</dt>
          <dd className="num">{formatCurrency(marked?.toTarget ?? toTarget.dollars)}</dd>
        </div>
        <div>
          <dt className="micro">Shares</dt>
          <dd className="num">{position.remaining_shares ?? position.shares}</dd>
        </div>
      </dl>
    </article>
  );
}

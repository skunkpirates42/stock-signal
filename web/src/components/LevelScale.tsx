import type { Direction } from "@/lib/types";
import { entryFraction, entryLabelAnchor } from "@/lib/levels";
import { formatPrice } from "@/lib/format";

export interface LevelScaleProps {
  stop: number;
  entry: number;
  target: number;
  direction: Direction;
  current?: number;
}

export default function LevelScale({ stop, entry, target, direction, current }: LevelScaleProps) {
  const fraction = entryFraction(stop, entry, target);
  if (fraction === null) {
    return <p className="level-scale-empty">Stop and target are the same price.</p>;
  }

  const offset = Math.min(1, Math.max(0, fraction));
  const malformed = fraction < 0 || fraction > 1;

  return (
    <div className="level-scale">
      <div className="level-scale-track">
        <span className="level-scale-risk" style={{ width: `${offset * 100}%` }} />
        {current !== undefined && (
          <span
            className="level-scale-current"
            title={`Last price ${formatPrice(current)} (clamped to scale)`}
            style={{
              left: `${Math.min(1, Math.max(0, (current - stop) / (target - stop))) * 100}%`,
            }}
          />
        )}
        <span className="level-scale-entry" style={{ left: `${offset * 100}%` }} />
      </div>
      <div className="level-scale-labels">
        <span className="tone-negative num">{formatPrice(stop)}</span>
        <span className="tone-positive num">{formatPrice(target)}</span>
      </div>
      <div className="level-scale-entry-label">
        <span
          className={`num level-scale-entry-label-${entryLabelAnchor(offset)}`}
          style={{ left: `${offset * 100}%` }}
        >
          {formatPrice(entry)}
        </span>
      </div>
      <p className="micro level-scale-legend">
        Stop · Entry · Target ({direction}){current !== undefined ? " · Diamond: last price" : ""}
      </p>
      {malformed && (
        <p className="level-scale-warning">
          Entry sits outside its own stop and target. This level set is malformed.
        </p>
      )}
    </div>
  );
}

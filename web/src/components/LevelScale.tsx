import type { Direction } from "@/lib/types";
import { entryFraction, entryLabelAnchor } from "@/lib/levels";
import { formatPrice } from "@/lib/format";

export interface LevelScaleProps {
  stop: number;
  entry: number;
  target: number;
  direction: Direction;
}

export default function LevelScale({ stop, entry, target, direction }: LevelScaleProps) {
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
        Stop · Entry · Target ({direction})
      </p>
      {malformed && (
        <p className="level-scale-warning">
          Entry sits outside its own stop and target. This level set is malformed.
        </p>
      )}
    </div>
  );
}

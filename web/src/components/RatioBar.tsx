export interface RatioBarProps {
  left: number;
  right: number;
  leftLabel: string;
  rightLabel: string;
}

export default function RatioBar({ left, right, leftLabel, rightLabel }: RatioBarProps) {
  const total = left + right;
  const leftPercent = total === 0 ? 0 : (left / total) * 100;

  return (
    <div className="ratio">
      <div
        className="ratio-track"
        role="img"
        aria-label={`${left} ${leftLabel}, ${right} ${rightLabel}`}
      >
        <div className="ratio-fill-left" style={{ width: `${leftPercent}%` }} />
      </div>
      <div className="ratio-legend">
        <span className="tone-positive num">
          {left} {leftLabel}
        </span>
        <span className="tone-negative num">
          {right} {rightLabel}
        </span>
      </div>
    </div>
  );
}

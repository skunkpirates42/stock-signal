import { CONFIDENCE_THRESHOLD } from "@/lib/indicators";
import { formatPercent } from "@/lib/format";

export interface ConfidenceMeterProps {
  confidence: number;
}

export default function ConfidenceMeter({ confidence }: ConfidenceMeterProps) {
  const cleared = confidence >= CONFIDENCE_THRESHOLD;

  return (
    <span className="meter" title={`Threshold ${formatPercent(CONFIDENCE_THRESHOLD)}`}>
      <span className="meter-track">
        <span
          className={`meter-fill${cleared ? " meter-fill-cleared" : ""}`}
          style={{ width: `${Math.min(100, Math.max(0, confidence * 100))}%` }}
        />
        <span className="meter-threshold" style={{ left: `${CONFIDENCE_THRESHOLD * 100}%` }} />
      </span>
      <span className="meter-value num">{formatPercent(confidence)}</span>
    </span>
  );
}

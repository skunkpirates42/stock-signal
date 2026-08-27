import type { Direction, Signal, Trade } from "@/lib/types";
import { formatTimestamp } from "@/lib/format";
import ConfidenceMeter from "@/components/ConfidenceMeter";
import RationalePanel from "@/components/RationalePanel";

export interface SignalRowProps {
  signal: Signal;
  outcome: Trade["outcome"] | null;
  expanded: boolean;
  onToggle: () => void;
}

function directionClass(direction: Direction): string {
  if (direction === "LONG") return "tone-positive";
  if (direction === "SHORT") return "tone-negative";
  return "tone-muted";
}

function outcomeClass(outcome: Trade["outcome"]): string {
  if (outcome === "WIN") return "tone-positive";
  if (outcome === "LOSS") return "tone-negative";
  return "tone-muted";
}

export default function SignalRow({ signal, outcome, expanded, onToggle }: SignalRowProps) {
  return (
    <div className="signal-row">
      <button
        type="button"
        className="signal-row-summary"
        onClick={onToggle}
        aria-expanded={expanded}
      >
        <span className="signal-row-ticker">{signal.ticker}</span>
        <span className={`signal-badge ${directionClass(signal.direction)}`}>
          {signal.direction}
        </span>
        <ConfidenceMeter confidence={signal.confidence} />
        <span className="signal-row-outcome">
          {outcome && <span className={`signal-badge ${outcomeClass(outcome)}`}>{outcome}</span>}
        </span>
        <span className="signal-row-timestamp num">
          {formatTimestamp(signal.bar_timestamp ?? signal.created_at)}
        </span>
      </button>
      {expanded && (
        <div className="signal-row-detail">
          <RationalePanel signal={signal} />
        </div>
      )}
    </div>
  );
}

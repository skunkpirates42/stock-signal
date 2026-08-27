import type { Signal } from "@/lib/types";
import { parseIndicators, voteTally } from "@/lib/indicators";
import { formatPrice, formatRatio } from "@/lib/format";
import VoteTable from "@/components/VoteTable";

export interface RationalePanelProps {
  signal: Signal;
}

function provenanceLabel(source: string | null): string {
  return source ?? "provenance not recorded";
}

export default function RationalePanel({ signal }: RationalePanelProps) {
  const rows = parseIndicators(signal.indicators_json);
  const tally = voteTally(rows);

  return (
    <div className="rationale-panel">
      <div className="rationale-reasoning">
        <p>{signal.reasoning ?? "No reasoning recorded for this signal."}</p>
        <p className="rationale-provenance">Source: {provenanceLabel(signal.synthesis_source)}</p>
      </div>

      <div className="rationale-votes">
        <h3>
          Votes — {tally.bull} bull / {tally.bear} bear / {tally.neutral} neutral
        </h3>
        <VoteTable rows={rows} />
      </div>

      <div className="rationale-levels">
        {signal.direction === "WAIT" ? (
          <p className="rationale-wait-note">
            The engine stood aside — indicator agreement fell short of the threshold, so no
            entry, stop, or target was set.
          </p>
        ) : (
          <dl className="rationale-level-grid">
            <div>
              <dt>Entry</dt>
              <dd>{formatPrice(signal.entry)}</dd>
            </div>
            <div>
              <dt>Stop</dt>
              <dd>{formatPrice(signal.stop)}</dd>
            </div>
            <div>
              <dt>Target</dt>
              <dd>{formatPrice(signal.target)}</dd>
            </div>
            <div>
              <dt>R:R</dt>
              <dd>{formatRatio(signal.rr)}</dd>
            </div>
          </dl>
        )}
      </div>
    </div>
  );
}

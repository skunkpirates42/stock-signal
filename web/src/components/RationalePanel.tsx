import type { Signal } from "@/lib/types";
import {
  atrArithmetic,
  parseAtr,
  parseIndicators,
  parseVolumeRatio,
  voteTally,
} from "@/lib/indicators";
import { formatPrice, formatRatio } from "@/lib/format";
import LevelScale from "@/components/LevelScale";
import SignalReasoning from "@/components/SignalReasoning";
import VoteTable from "@/components/VoteTable";

export interface RationalePanelProps {
  signal: Signal;
}

export default function RationalePanel({ signal }: RationalePanelProps) {
  const rows = parseIndicators(signal.indicators_json);
  const tally = voteTally(rows);
  const atr = parseAtr(signal.indicators_json);
  const arithmetic =
    atr !== null && signal.direction !== "WAIT" ? atrArithmetic(signal.direction, atr) : null;
  const volumeRatio = parseVolumeRatio(signal.indicators_json);

  return (
    <div className="rationale-panel">
      <div className="rationale-columns">
        <SignalReasoning
          signalId={signal.id}
          reasoning={signal.reasoning}
          synthesisSource={signal.synthesis_source}
        />

        <div className="rationale-votes">
          <h3>
            Votes — {tally.bull} bull / {tally.bear} bear / {tally.neutral} neutral
          </h3>
          <VoteTable rows={rows} />
          {volumeRatio !== null && (
            <p className="rationale-volume-note">
              Confidence also factors in a volume modifier (volume ratio{" "}
              {volumeRatio.toFixed(2)}×) beyond these six directional votes.
            </p>
          )}
        </div>

        <div className="rationale-levels">
          {signal.direction !== "WAIT" &&
            signal.entry !== null &&
            signal.stop !== null &&
            signal.target !== null && (
              <LevelScale
                stop={signal.stop}
                entry={signal.entry}
                target={signal.target}
                direction={signal.direction}
              />
            )}
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
          {arithmetic && signal.entry !== null && (
            <p className="rationale-atr-note">
              Stop = entry {arithmetic.stopOperator} (ATR × {arithmetic.stopMultiplier.toFixed(1)})
              {" "}= {formatPrice(signal.entry)} {arithmetic.stopOperator} (
              {formatPrice(arithmetic.atr)} × {arithmetic.stopMultiplier.toFixed(1)})
              <br />
              Target = entry {arithmetic.targetOperator} (ATR ×{" "}
              {arithmetic.targetMultiplier.toFixed(1)}) = {formatPrice(signal.entry)}{" "}
              {arithmetic.targetOperator} ({formatPrice(arithmetic.atr)} ×{" "}
              {arithmetic.targetMultiplier.toFixed(1)})
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

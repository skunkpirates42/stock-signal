import IntentPrefetchLink from "@/components/IntentPrefetchLink";
import { sampleWarning } from "@/lib/provenance";

export interface ProvenanceBandProps {
  source: "live" | "all";
  /** Total closed trades in the current view. */
  nClosed: number;
  /** How many of those closed trades are live (as opposed to backtest replay). */
  nLiveClosed: number;
}

export default function ProvenanceBand({ source, nClosed, nLiveClosed }: ProvenanceBandProps) {
  const isLive = source === "live";
  const warning = sampleWarning(source, nClosed, nLiveClosed);

  return (
    <div className="provenance">
      <p className="provenance-statement note">
        {isLive ? (
          <>
            Showing {nClosed} live trades. Backtest rows excluded.{" "}
            <IntentPrefetchLink href="/?source=all">Include backtest rows</IntentPrefetchLink>
          </>
        ) : (
          <>
            Showing {nClosed} trades, live and backtest replay combined.{" "}
            <IntentPrefetchLink href="/">Show live trades only</IntentPrefetchLink>
          </>
        )}
      </p>
      {warning && (
        <p className="provenance-warning">
          <span aria-hidden="true">⚠ </span>
          {warning}
        </p>
      )}
    </div>
  );
}

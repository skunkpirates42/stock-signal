import Link from "next/link";
import { PROVISIONAL_FLOOR, isProvisional } from "@/lib/provenance";

export interface ProvenanceBandProps {
  source: "live" | "all";
  /** Total closed trades in the current view. */
  nClosed: number;
  /** How many of those closed trades are live (as opposed to backtest replay). */
  nLiveClosed: number;
}

export default function ProvenanceBand({ source, nClosed, nLiveClosed }: ProvenanceBandProps) {
  const isLive = source === "live";
  const nBacktestClosed = nClosed - nLiveClosed;

  return (
    <div className="provenance-band">
      <p className="provenance-statement">
        {isLive ? (
          <>
            Showing {nClosed} live trades. Backtest rows excluded.{" "}
            <Link href="/?source=all">Include backtest rows</Link>
          </>
        ) : (
          <>
            Showing {nClosed} trades, live and backtest replay combined.{" "}
            <Link href="/">Show live trades only</Link>
          </>
        )}
      </p>
      {isLive && isProvisional(nClosed) && (
        <p className="provenance-warning">
          Provisional: only {nClosed} closed trades. The project&apos;s evaluation floor is
          {" "}{PROVISIONAL_FLOOR} closed trades — no conclusion should be drawn from this
          sample yet.
        </p>
      )}
      {!isLive && (
        <p className="provenance-warning">
          Only {nLiveClosed} of these {nClosed} closed trades are live; the other{" "}
          {nBacktestClosed} are backtest replay of a different period. These blended figures
          are not a live track record — switch to the live-only view above for the real sample.
        </p>
      )}
    </div>
  );
}

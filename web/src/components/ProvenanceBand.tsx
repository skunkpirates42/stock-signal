import Link from "next/link";

const PROVISIONAL_FLOOR = 50;

export interface ProvenanceBandProps {
  source: "live" | "all";
  nClosed: number;
}

export default function ProvenanceBand({ source, nClosed }: ProvenanceBandProps) {
  const isLive = source === "live";
  const isProvisional = nClosed < PROVISIONAL_FLOOR;

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
      {isProvisional && (
        <p className="provenance-warning">
          Provisional: only {nClosed} closed trades. The project&apos;s evaluation floor is
          50 closed trades — no conclusion should be drawn from this sample yet.
        </p>
      )}
    </div>
  );
}

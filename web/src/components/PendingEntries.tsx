import { observationFresh, type PositionState } from "@/lib/execution";
import { formatPrice } from "@/lib/format";

export default function PendingEntries({
  entries,
  isBrokerObservationCurrent,
  now,
}: {
  entries: PositionState["pending_entries"];
  isBrokerObservationCurrent: boolean;
  now: Date;
}) {
  return (
    <>
      {entries.map((entry) => (
        <div className="card stack stack-detail" key={entry.id}>
          <p>
            {entry.ticker} · pending Alpaca paper entry · {entry.state}
          </p>
          <p>
            Requested {entry.requested_qty} · filled {entry.filled_qty} · actual average{" "}
            {formatPrice(entry.fill_price)} · protection awaiting entry fill
          </p>
          {entry.pending_exit && <p>Pending exit: {entry.pending_exit}</p>}
          {Object.entries(entry.execution?.legs ?? {}).map(([kind, leg]) => (
            <p key={kind}>
              {kind === "stop" ? "Stop" : "Target"}{" "}
              {formatPrice(kind === "stop" ? entry.stop : entry.target)} · {leg.state}
              {leg.state === "held" ? " · awaiting activation" : ""}
              {" · not confirmed active"}
              {!isBrokerObservationCurrent || !observationFresh(leg.updated_at ?? null, now)
                ? " · observation stale/unknown"
                : ""}
            </p>
          ))}
        </div>
      ))}
    </>
  );
}

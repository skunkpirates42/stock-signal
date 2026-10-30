import type { ExecutionPosition } from "@/lib/execution";
import { observationFresh } from "@/lib/execution";
import { formatPrice } from "@/lib/format";

export default function PositionExecution({
  position,
  current,
  now,
}: {
  position: ExecutionPosition;
  current: boolean;
  now: Date;
}) {
  const execution = position.execution;
  if (!execution) return null;
  const entry = execution.entry;
  const protectedNow =
    current &&
    execution.protection === "confirmed" &&
    Object.values(execution.legs).every((leg) => observationFresh(leg.updated_at ?? null, now));
  return (
    <div className="card stack stack-detail">
      <p>
        {position.ticker} · Alpaca paper · {position.account} · trade #{position.id}
      </p>
      <p>
        Entry: {entry?.state ?? "unknown"} · requested {entry?.requested_qty ?? "unknown"} · filled{" "}
        {entry?.filled_qty ?? "unknown"} · actual average {formatPrice(entry?.fill_price ?? null)}
      </p>
      <p>Remaining quantity: {position.remaining_shares ?? "unknown"}</p>
      <p role="status">
        {protectedNow
          ? "Protection confirmed at last observation"
          : "Warning: current protection is not confirmed"}
      </p>
      {Object.entries(execution.legs).map(([kind, leg]) => (
        <p key={kind}>
          {kind === "stop" ? "Stop" : "Target"}{" "}
          {formatPrice(kind === "stop" ? position.stop : position.target)} · {leg.state}
          {leg.state === "held" ? " (awaiting activation; not confirmed active)" : ""}
          {leg.state === "missing" ? " (missing or ambiguous identity)" : ""}
          {" · quantity "}
          {leg.quantity ?? "unknown"}
          {!leg.coverage ? " · coverage incomplete" : ""}
          {!current || !leg.current || !observationFresh(leg.updated_at ?? null, now)
            ? " · observation stale/unknown"
            : ""}
        </p>
      ))}
      {execution.pending_exit && <p role="status">Pending exit: {execution.pending_exit}</p>}
    </div>
  );
}

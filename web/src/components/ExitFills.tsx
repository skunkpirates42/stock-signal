import type { PositionState } from "@/lib/execution";
import { formatPrice, formatTimestamp } from "@/lib/format";

export default function ExitFills({ fills }: { fills: PositionState["exit_fills"] }) {
  return (
    <section className="stack" aria-label="Actual broker exit fills">
      <h2>Actual broker exit fills</h2>
      <p className="micro">
        Confirmed cumulative fills from the journal; prices below are broker fills, not IEX
        estimates.
      </p>
      {fills.map((fill) => (
        <p key={fill.id}>
          {fill.ticker} · {fill.reason ?? "exit"} · {fill.state} · {fill.filled_qty} shares at{" "}
          {formatPrice(fill.fill_price)} · recorded {formatTimestamp(fill.updated_at)}
        </p>
      ))}
    </section>
  );
}

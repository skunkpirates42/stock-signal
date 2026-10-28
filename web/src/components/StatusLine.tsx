import Disclosure from "@/components/Disclosure";
import type { StatusSummary } from "@/lib/health";

export interface StatusLineProps {
  summary: StatusSummary;
  error: string | null;
}

export default function StatusLine({ summary, error }: StatusLineProps) {
  return (
    <aside className="status-line" aria-live="polite">
      <Disclosure
        summary={
          <>
            <span>{summary.scope}</span>
            <span className={`status-api-${summary.api}`}>API {summary.api}</span>
            <span className={`status-heartbeat-${summary.heartbeat}`}>
              Heartbeat {summary.heartbeat}
            </span>
            {summary.runtime
              .filter((row) => row.status !== "running")
              .map((row) => (
                <span className="status-attention" key={row.scope}>
                  {row.scope}: {row.status}
                </span>
              ))}
            {summary.unresolvedOrders.length > 0 && (
              <span className="status-attention">
                {summary.unresolvedOrders.length} unresolved{" "}
                {summary.unresolvedOrders.length === 1 ? "order" : "orders"}
              </span>
            )}
          </>
        }
      >
        <div className="status-detail">
          <p>API checked: {summary.checkedAt ?? "pending"}</p>
          <p>
            Latest live signal bar: {summary.latestBar ?? "none recorded"}. API refresh does not
            establish stream health.
          </p>
          {summary.runtime.map((row) => (
            <p key={row.scope}>
              {row.scope}: {row.status} · heartbeat {row.heartbeat} ({row.updated_at}) · latest data{" "}
              {row.data_at ?? "none"} · {row.detail}
            </p>
          ))}
        </div>
      </Disclosure>
      {error && <p role="alert">{error}</p>}
      {summary.unresolvedOrders.map((order) => (
        <p className="status-attention" key={order.id}>
          {order.ticker} {order.purpose}: {order.state} · confirmed {order.filled_qty}/
          {order.requested_qty} shares
        </p>
      ))}
    </aside>
  );
}

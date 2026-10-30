import Disclosure from "@/components/Disclosure";
import type { StatusSummary } from "@/lib/health";

export interface StatusLineProps {
  summary: StatusSummary;
  error: string | null;
  marketLabel?: string;
  marketCheckedAt?: string;
}

export default function StatusLine({
  summary,
  error,
  marketLabel,
  marketCheckedAt,
}: StatusLineProps) {
  return (
    <aside className="status-line" aria-live="polite">
      <Disclosure
        summary={
          <>
            <span>{summary.scope}</span>
            <span>{marketLabel ?? "US regular market: unavailable"}</span>
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
          </>
        }
      >
        <div className="status-detail">
          <p>
            Market clock checked: {marketCheckedAt ?? "pending"}. Regular US equity session;
            extended hours are excluded.
          </p>
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
    </aside>
  );
}

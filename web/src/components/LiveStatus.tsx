"use client";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getOperationalStatus } from "@/lib/actions";
import { heartbeatState } from "@/lib/health";
import { startVisiblePolling } from "@/lib/polling";

export default function LiveStatus() {
  const router = useRouter();
  const source = useSearchParams().get("source") === "all" ? "all sources" : "live";
  const [status, setStatus] = useState<Awaited<ReturnType<typeof getOperationalStatus>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checked, setChecked] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    const stop = startVisiblePolling(async () => {
      try {
        const result = await getOperationalStatus();
        if (!active) return;
        setStatus(result);
        setError(null);
        setChecked(new Date().toISOString());
        router.refresh();
      } catch {
        if (active) setError("API unavailable. Displayed records may be stale.");
      }
    }, document);
    return () => { active = false; stop(); };
  }, [router]);
  return <aside className="micro" aria-live="polite">
    <p>Scope: {source} · API checked: {checked ?? "pending"}</p>
    {error && <p role="alert">{error}</p>}
    <p>Latest live signal bar: {status?.latest_bar ?? "none recorded"}. API refresh does not establish stream health.</p>
    {status?.runtime.map(row => <p key={row.scope}>
      {row.scope}: {row.status} · heartbeat {heartbeatState(row.updated_at, Date.parse(checked ?? row.updated_at))} ({row.updated_at}) · latest data {row.data_at ?? "none"} · {row.detail}
    </p>)}
    {status?.unresolved_orders.map(order => <p key={order.id}>
      {order.ticker} {order.purpose}: {order.state} · confirmed {order.filled_qty}/{order.requested_qty} shares
    </p>)}
  </aside>;
}

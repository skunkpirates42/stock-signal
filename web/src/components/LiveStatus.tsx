"use client";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { usePolledResource } from "@/hooks/usePolledResource";
import { useVisibleClock } from "@/hooks/useVisibleClock";
import { getOperationalStatus } from "@/lib/actions";
import {
  describeStatus,
  marketStatusLabel,
  readMarketStatus,
  type OperationalStatus,
} from "@/lib/health";
import { startVisiblePolling } from "@/lib/polling";
import StatusLine from "@/components/StatusLine";

export default function LiveStatus() {
  const router = useRouter();
  const marketPoll = usePolledResource("/api/market-status", readMarketStatus, 15000);
  const market = marketPoll.failed ? null : marketPoll.data;
  const marketCheckedAt = useVisibleClock(1000).getTime();
  const source = useSearchParams().get("source");
  const [status, setStatus] = useState<OperationalStatus | null>(null);
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
    return () => {
      active = false;
      stop();
    };
  }, [router]);
  const summary = describeStatus({ source, status, apiFailed: error !== null, checkedAt: checked });
  return (
    <StatusLine
      summary={summary}
      error={error}
      marketLabel={marketStatusLabel(market, marketCheckedAt)}
      marketCheckedAt={market?.checked_at}
    />
  );
}

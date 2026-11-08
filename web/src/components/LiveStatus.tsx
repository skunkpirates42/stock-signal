"use client";

import { useSearchParams } from "next/navigation";
import { usePolledResource } from "@/hooks/usePolledResource";
import { useVisibleClock } from "@/hooks/useVisibleClock";
import {
  describeStatus,
  marketStatusLabel,
  readMarketStatus,
  readOperationalStatus,
} from "@/lib/health";
import StatusLine from "@/components/StatusLine";

export default function LiveStatus() {
  const marketPoll = usePolledResource("/api/market-status", readMarketStatus, 15_000);
  const statusPoll = usePolledResource("/api/operational-status", readOperationalStatus, 15_000);
  const market = marketPoll.failed ? null : marketPoll.data;
  const marketCheckedAt = useVisibleClock(1000).getTime();
  const source = useSearchParams().get("source");
  const error = statusPoll.failed
    ? "Status update unavailable. Displayed records may be stale."
    : null;
  const summary = describeStatus({
    source,
    status: statusPoll.data,
    apiFailed: statusPoll.failed,
    checkedAt: statusPoll.checkedAt?.toISOString() ?? null,
  });
  return (
    <StatusLine
      summary={summary}
      error={error}
      marketLabel={marketStatusLabel(market, marketCheckedAt)}
      marketCheckedAt={market?.checked_at}
    />
  );
}

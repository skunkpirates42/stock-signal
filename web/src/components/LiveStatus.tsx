"use client";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getOperationalStatus } from "@/lib/actions";
import {
  describeStatus,
  marketStatusLabel,
  type MarketStatus,
  type OperationalStatus,
} from "@/lib/health";
import { startVisiblePolling } from "@/lib/polling";
import StatusLine from "@/components/StatusLine";

export default function LiveStatus() {
  const router = useRouter();
  const [market, setMarket] = useState<MarketStatus | null>(null);
  const [marketChecked, setMarketChecked] = useState(0);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const refreshAge = () => {
      if (document.visibilityState === "visible") setMarketChecked(Date.now());
    };
    const timer = setInterval(refreshAge, 1000);
    document.addEventListener("visibilitychange", refreshAge);
    const stop = startVisiblePolling(
      async () => {
        refreshAge();
        try {
          const response = await fetch("/api/market-status", {
            cache: "no-store",
            signal: AbortSignal.any([controller.signal, AbortSignal.timeout(6000)]),
          });
          if (!response.ok) throw new Error("Market status unavailable");
          const result: MarketStatus = await response.json();
          if (active) setMarket(result);
        } catch {
          if (active) setMarket(null);
        } finally {
          if (active) setMarketChecked(Date.now());
        }
      },
      document,
      15000,
    );
    return () => {
      active = false;
      controller.abort();
      clearInterval(timer);
      document.removeEventListener("visibilitychange", refreshAge);
      stop();
    };
  }, []);
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
      marketLabel={marketStatusLabel(market, marketChecked)}
      marketCheckedAt={market?.checked_at}
    />
  );
}

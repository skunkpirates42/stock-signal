"use client";

import { useCallback, useEffect, useRef, useTransition } from "react";
import { useRouter } from "next/navigation";
import { startVisiblePolling } from "@/lib/polling";

export function useRouteRefresh(intervalMs: number | null) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const refreshing = useRef(false);

  useEffect(() => {
    if (!pending) refreshing.current = false;
  }, [pending]);

  const refresh = useCallback(() => {
    if (refreshing.current) return;
    refreshing.current = true;
    startTransition(() => router.refresh());
  }, [router]);

  useEffect(() => {
    if (intervalMs === null) return;
    return startVisiblePolling(async () => refresh(), document, intervalMs, false);
  }, [intervalMs, refresh]);

  return refresh;
}

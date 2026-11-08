"use client";

import { useRouteRefresh } from "@/hooks/useRouteRefresh";

export default function ServerDataRefresh() {
  useRouteRefresh(15_000);
  return null;
}

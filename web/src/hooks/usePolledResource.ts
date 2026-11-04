"use client";

import { useEffect, useState } from "react";
import type { Read } from "@/lib/parse";
import { NOT_YET_POLLED, startPolledResource, type PolledResource } from "@/lib/polledResource";

// `read` must be stable across renders (a module-level reader), or polling restarts.
export function usePolledResource<T>(
  url: string | null,
  read: Read<T>,
  intervalMs: number,
): PolledResource<T> {
  const [resource, setResource] = useState<PolledResource<T>>(NOT_YET_POLLED);
  useEffect(() => {
    if (url === null) return;
    return startPolledResource(url, read, setResource, document, intervalMs);
  }, [url, read, intervalMs]);
  return resource;
}

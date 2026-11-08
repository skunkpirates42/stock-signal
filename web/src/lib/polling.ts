/** Visibility-aware scheduling, injectable for lifecycle tests. */
export function startVisiblePolling(
  task: () => Promise<void>,
  doc: Pick<Document, "visibilityState" | "addEventListener" | "removeEventListener">,
  delay = 15000,
  immediately = true,
) {
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let running = false;
  const poll = async () => {
    if (stopped || running || doc.visibilityState !== "visible") return;
    running = true;
    try {
      await task();
    } finally {
      running = false;
      if (!stopped && doc.visibilityState === "visible") timer = setTimeout(poll, delay);
    }
  };
  const visibility = () => {
    clearTimeout(timer);
    if (doc.visibilityState === "visible") void poll();
  };
  doc.addEventListener("visibilitychange", visibility);
  if (immediately) void poll();
  else if (doc.visibilityState === "visible") timer = setTimeout(poll, delay);
  return () => {
    stopped = true;
    clearTimeout(timer);
    doc.removeEventListener("visibilitychange", visibility);
  };
}

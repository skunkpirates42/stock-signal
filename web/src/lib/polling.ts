/** Visibility-aware scheduling, injectable for lifecycle tests. */
export function startVisiblePolling(
  task: () => Promise<void>,
  doc: Pick<Document, "visibilityState" | "addEventListener" | "removeEventListener">,
  delay = 15000,
) {
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let running = false;
  const poll = async () => {
    if (stopped || running || doc.visibilityState !== "visible") return;
    running = true;
    try { await task(); }
    finally {
      running = false;
      if (!stopped && doc.visibilityState === "visible") timer = setTimeout(poll, delay);
    }
  };
  const visibility = () => {
    clearTimeout(timer);
    if (doc.visibilityState === "visible") void poll();
  };
  doc.addEventListener("visibilitychange", visibility);
  void poll();
  return () => {
    stopped = true;
    clearTimeout(timer);
    doc.removeEventListener("visibilitychange", visibility);
  };
}

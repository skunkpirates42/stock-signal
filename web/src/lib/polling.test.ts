import { afterEach, expect, it, vi } from "vitest";
import { startVisiblePolling } from "./polling";

afterEach(() => vi.useRealTimers());
it("refreshes visible pages, pauses hidden pages, and cleans up", async () => {
  vi.useFakeTimers();
  let callback: (() => void) | undefined;
  const doc = {
    visibilityState: "visible" as DocumentVisibilityState,
    addEventListener: vi.fn((_name: string, cb: unknown) => { callback = cb as () => void; }),
    removeEventListener: vi.fn(),
  };
  const task = vi.fn(async () => {});
  const stop = startVisiblePolling(task, doc as unknown as Document, 100);
  await vi.advanceTimersByTimeAsync(100);
  expect(task).toHaveBeenCalledTimes(2);
  doc.visibilityState = "hidden"; callback!();
  await vi.advanceTimersByTimeAsync(500);
  expect(task).toHaveBeenCalledTimes(2);
  doc.visibilityState = "visible"; callback!();
  await vi.advanceTimersByTimeAsync(0);
  expect(task).toHaveBeenCalledTimes(3);
  stop();
  await vi.advanceTimersByTimeAsync(500);
  expect(task).toHaveBeenCalledTimes(3);
  expect(doc.removeEventListener).toHaveBeenCalled();
});

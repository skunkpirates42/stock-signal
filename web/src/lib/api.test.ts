import { afterEach, expect, it, vi } from "vitest";
import { getMetrics, READ_TIMEOUT_MS } from "./api";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("rejects instead of hanging when Flask never responds", async () => {
  const timeout = new AbortController();
  const timeoutSpy = vi.spyOn(AbortSignal, "timeout").mockReturnValue(timeout.signal);
  vi.stubGlobal(
    "fetch",
    vi.fn(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => reject(init.signal?.reason));
        }),
    ),
  );

  const metrics = getMetrics();
  timeout.abort(new DOMException("The operation timed out.", "TimeoutError"));

  await expect(metrics).rejects.toMatchObject({ name: "TimeoutError" });
  expect(timeoutSpy).toHaveBeenCalledWith(READ_TIMEOUT_MS);
});

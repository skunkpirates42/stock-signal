import { describe, expect, it, vi } from "vitest";

const notFoundError = () => Object.assign(new Error("missing"), { name: "DemoNotFound" });

vi.mock("@/lib/jobs", () => ({ getJob: vi.fn() }));
vi.mock("@/lib/demo", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/demo")>()),
  savedResultExists: vi.fn(),
}));

import Page from "./page";
import { getJob } from "@/lib/jobs";
import { savedResultExists } from "@/lib/demo";

const params = (runId: string) => ({ params: Promise.resolve({ runId }) });

describe("run page", () => {
  it("renders a job without checking saved results", async () => {
    vi.mocked(getJob).mockResolvedValueOnce({ data: { run: {}, status: {} }, warnings: [] } as never);
    const page = await Page(params("job-uuid"));
    expect(page).toBeTruthy();
    expect(savedResultExists).not.toHaveBeenCalled();
  });

  it("redirects an old saved-result link to its research route", async () => {
    vi.mocked(getJob).mockRejectedValueOnce(notFoundError());
    vi.mocked(savedResultExists).mockResolvedValueOnce(true);
    await expect(Page(params("result-uuid"))).rejects.toMatchObject({
      digest: expect.stringContaining("/research/result-uuid"),
    });
  });

  it("is not found when the ID is neither a job nor a saved result", async () => {
    vi.mocked(getJob).mockRejectedValueOnce(notFoundError());
    vi.mocked(savedResultExists).mockResolvedValueOnce(false);
    await expect(Page(params("missing-uuid"))).rejects.toMatchObject({ digest: "NEXT_HTTP_ERROR_FALLBACK;404" });
  });

  it("surfaces a job store failure instead of guessing", async () => {
    vi.mocked(getJob).mockRejectedValueOnce(new Error("/runs/x responded 500"));
    await expect(Page(params("job-uuid"))).rejects.toThrow("responded 500");
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";
import { getSavedDiagnostics, type Artifact } from "@/lib/demo";

const RESULT_ID = "123e4567-e89b-12d3-a456-426614174000";
const ARTIFACT_ID = "123e4567-e89b-12d3-a456-426614174001";
const artifact: Artifact = {
  record_type: "artifact",
  id: ARTIFACT_ID,
  result_id: RESULT_ID,
  kind: "diagnostics",
  sha256: "a".repeat(64),
  mime_type: "application/json",
  byte_size: 128,
};

afterEach(() => vi.restoreAllMocks());

describe("saved diagnostics adapter", () => {
  it("returns only verified saved aggregate count maps", async () => {
    const body = JSON.stringify({
      signal_execution_reasons: { quality_gate: 3, wait: 0 },
      candidate_gate_checks: { accepted: 4, rejected: 1 },
      unrelated: { pnl: 999 },
    });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(body, { status: 200, headers: {
      "content-type": "application/json", "content-length": String(new TextEncoder().encode(body).byteLength),
    } })));

    const result = await getSavedDiagnostics(RESULT_ID, [artifact]);

    expect(result).toEqual({
      availability: "available",
      value: {
        signal_execution_reasons: { quality_gate: 3, wait: 0 },
        candidate_gate_checks: { accepted: 4, rejected: 1 },
      },
      reason: null,
      detail: "Saved aggregate counts from the indexed diagnostics artifact.",
    });
    expect(fetch).toHaveBeenCalledWith(
      `http://127.0.0.1:8000/api/demo/v1/results/${RESULT_ID}/artifacts/${ARTIFACT_ID}`,
      { cache: "no-store", redirect: "manual" },
    );
  });

  it("keeps missing, unbounded, or malformed diagnostics unavailable", async () => {
    await expect(getSavedDiagnostics(RESULT_ID, [])).resolves.toMatchObject({ availability: "unavailable", reason: "missing_artifact" });

    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200, headers: { "content-type": "application/json" } })));
    await expect(getSavedDiagnostics(RESULT_ID, [artifact])).resolves.toMatchObject({ availability: "unavailable", reason: "unverified" });

    vi.stubGlobal("fetch", vi.fn(async () => new Response("body larger than declared", { status: 200, headers: {
      "content-type": "application/json", "content-length": "2",
    } })));
    await expect(getSavedDiagnostics(RESULT_ID, [artifact])).resolves.toMatchObject({ availability: "unavailable", reason: "unverified" });

    const invalid = JSON.stringify({ signal_execution_reasons: { wait: -1 }, candidate_gate_checks: { accepted: 1 } });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(invalid, { status: 200, headers: {
      "content-type": "application/json", "content-length": String(invalid.length),
    } })));
    await expect(getSavedDiagnostics(RESULT_ID, [artifact])).resolves.toMatchObject({ availability: "unavailable", reason: "unverified" });
  });

  it("rejects a diagnostics reference owned by another result before fetching", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(getSavedDiagnostics(RESULT_ID, [{ ...artifact, result_id: "123e4567-e89b-12d3-a456-426614174099" }]))
      .resolves.toMatchObject({ availability: "unavailable", reason: "unverified" });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

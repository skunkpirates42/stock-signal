import "server-only";

import { API_BASE, READ_TIMEOUT_MS } from "@/lib/backend";
import type { Read } from "@/lib/parse";
import {
  isOpaqueDemoId,
  readEnvelope,
  readResearchPage,
  readSavedResultDetail,
  type Artifact,
  type Availability,
  type Envelope,
  type SavedDiagnostics,
} from "@/lib/demo/contracts";

export class DemoNotFound extends Error {
  override name = "DemoNotFound";
}

export async function demoGet<T>(path: string, readData: Read<T>): Promise<Envelope<T>> {
  const response = await fetch(`${API_BASE}/api/demo/v1${path}`, {
    cache: "no-store",
    redirect: "manual",
    signal: AbortSignal.timeout(READ_TIMEOUT_MS),
  });
  if (response.status === 404) throw new DemoNotFound("Demo record was not found");
  if (!response.ok) throw new Error(`${path} responded ${response.status}`);
  return readEnvelope(readData)(await response.json(), path);
}

export async function getResearchResults(cursor?: string) {
  if (cursor !== undefined && !isOpaqueDemoId(cursor))
    throw new DemoNotFound("Saved demo cursor was not found");
  const params = new URLSearchParams({ limit: "50" });
  if (cursor) params.set("cursor", cursor);
  return demoGet(`/research?${params}`, readResearchPage);
}

// The research route identifies the result; the saved normalized run has a separate ID.
export async function getSavedResult(resultId: string) {
  if (!isOpaqueDemoId(resultId)) throw new DemoNotFound("Saved demo result was not found");
  return demoGet(`/results/${encodeURIComponent(resultId)}`, readSavedResultDetail);
}

export async function savedResultExists(resultId: string): Promise<boolean> {
  try {
    await getSavedResult(resultId);
    return true;
  } catch (error) {
    if (error instanceof Error && error.name === "DemoNotFound") return false;
    throw error;
  }
}

const MAX_ARTIFACT_BYTES = 1024 * 1024;

function countMap(value: unknown): Record<string, number> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const entries = Object.entries(value);
  if (
    !entries.every(
      ([key, count]) =>
        key.length > 0 && typeof count === "number" && Number.isSafeInteger(count) && count >= 0,
    )
  )
    return null;
  return Object.fromEntries(entries);
}

async function readBoundedBody(
  response: Response,
  expectedBytes: number,
): Promise<Uint8Array | null> {
  if (!response.body) return null;
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > MAX_ARTIFACT_BYTES || total > expectedBytes) {
        await reader.cancel();
        return null;
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  if (total !== expectedBytes) return null;
  const body = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body;
}

export async function getSavedDiagnostics(
  resultId: string,
  artifacts: Artifact[],
): Promise<Availability<SavedDiagnostics>> {
  const artifact = artifacts.find((item) => item.kind === "diagnostics");
  if (!artifact) {
    return {
      availability: "unavailable",
      value: null,
      reason: "missing_artifact",
      detail: "No indexed diagnostics artifact is available for this result.",
    };
  }
  if (
    !isOpaqueDemoId(resultId) ||
    !isOpaqueDemoId(artifact.id) ||
    artifact.result_id !== resultId
  ) {
    return {
      availability: "unavailable",
      value: null,
      reason: "unverified",
      detail: "The indexed diagnostics reference is not valid for this result.",
    };
  }

  try {
    const response = await fetch(
      `${API_BASE}/api/demo/v1/results/${encodeURIComponent(resultId)}/artifacts/${encodeURIComponent(artifact.id)}`,
      { cache: "no-store", redirect: "manual", signal: AbortSignal.timeout(READ_TIMEOUT_MS) },
    );
    const contentType = response.headers.get("content-type")?.split(";", 1)[0].trim();
    const contentLength = response.headers.get("content-length");
    const declaredLength = contentLength === null ? Number.NaN : Number(contentLength);
    if (
      !response.ok ||
      contentType !== "application/json" ||
      !Number.isSafeInteger(declaredLength) ||
      declaredLength < 0 ||
      declaredLength > MAX_ARTIFACT_BYTES
    ) {
      return {
        availability: "unavailable",
        value: null,
        reason: "unverified",
        detail: "The saved diagnostics could not be verified as bounded JSON.",
      };
    }
    const body = await readBoundedBody(response, declaredLength);
    if (!body) throw new Error("Diagnostics length mismatch");
    const raw: unknown = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(body));
    if (typeof raw !== "object" || raw === null || Array.isArray(raw))
      throw new Error("Invalid diagnostics object");
    const record = raw as Record<string, unknown>;
    const signalReasons = countMap(record.signal_execution_reasons);
    const gateChecks = countMap(record.candidate_gate_checks);
    if (!signalReasons || !gateChecks) throw new Error("Unsupported diagnostics schema");
    return {
      availability: "available",
      value: { signal_execution_reasons: signalReasons, candidate_gate_checks: gateChecks },
      reason: null,
      detail: "Saved aggregate counts from the indexed diagnostics artifact.",
    };
  } catch {
    return {
      availability: "unavailable",
      value: null,
      reason: "unverified",
      detail:
        "The indexed diagnostics artifact does not contain the supported saved aggregate counts.",
    };
  }
}

import { API_BASE, READ_TIMEOUT_MS } from "@/lib/api";
import { logUpstreamError, logUpstreamStatus } from "@/lib/log";

const MAX_ARTIFACT_BYTES = 1024 * 1024;
const ALLOWED_TYPES = new Set(["application/json", "text/plain", "text/markdown"]);
const SAFE_HEADERS = { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };

export async function proxyArtifact(path: string): Promise<Response> {
  const upstreamPath = `/api/demo/v1${path}`;
  let upstream: Response;
  try {
    upstream = await fetch(`${API_BASE}${upstreamPath}`, {
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(READ_TIMEOUT_MS),
    });
  } catch (error) {
    logUpstreamError(upstreamPath, error);
    return new Response(null, { status: 502, headers: SAFE_HEADERS });
  }
  if (upstream.status === 404 || upstream.status === 413) {
    return new Response(null, { status: upstream.status, headers: SAFE_HEADERS });
  }
  if (upstream.status !== 200) {
    logUpstreamStatus(upstreamPath, upstream.status);
    return new Response(null, { status: 502, headers: SAFE_HEADERS });
  }

  const mimeType = upstream.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase();
  const declaredSize = upstream.headers.get("content-length");
  if (!mimeType || !ALLOWED_TYPES.has(mimeType) || !declaredSize || !/^\d+$/.test(declaredSize)) {
    return new Response(null, { status: 502, headers: SAFE_HEADERS });
  }
  const expectedBytes = Number(declaredSize);
  if (
    !Number.isSafeInteger(expectedBytes) ||
    expectedBytes < 0 ||
    expectedBytes > MAX_ARTIFACT_BYTES
  ) {
    return new Response(null, { status: 413, headers: SAFE_HEADERS });
  }
  if (!upstream.body) return new Response(null, { status: 502, headers: SAFE_HEADERS });

  const chunks: Uint8Array[] = [];
  let total = 0;
  const reader = upstream.body.getReader();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > MAX_ARTIFACT_BYTES || total > expectedBytes) {
        await reader.cancel();
        return new Response(null, { status: 413, headers: SAFE_HEADERS });
      }
      chunks.push(value);
    }
  } catch (error) {
    logUpstreamError(upstreamPath, error);
    return new Response(null, { status: 502, headers: SAFE_HEADERS });
  } finally {
    reader.releaseLock();
  }
  if (total !== expectedBytes) return new Response(null, { status: 502, headers: SAFE_HEADERS });

  const body = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new Response(body, {
    headers: { ...SAFE_HEADERS, "Content-Type": mimeType, "Content-Length": String(total) },
  });
}

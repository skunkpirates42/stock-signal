import { API_BASE } from "@/lib/api";
import { isOpaqueDemoId } from "@/lib/demo";

const MAX_ARTIFACT_BYTES = 1024 * 1024;
const ALLOWED_TYPES = new Set(["application/json", "text/plain", "text/markdown"]);
const SAFE_HEADERS = { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ resultId: string; artifactId: string }> },
) {
  const { resultId, artifactId } = await params;
  if (!isOpaqueDemoId(resultId) || !isOpaqueDemoId(artifactId)) {
    return new Response(null, { status: 404, headers: SAFE_HEADERS });
  }

  let upstream: Response;
  try {
    upstream = await fetch(
      `${API_BASE}/api/demo/v1/results/${resultId}/artifacts/${artifactId}`,
      { cache: "no-store", redirect: "manual" },
    );
  } catch {
    return new Response(null, { status: 502, headers: SAFE_HEADERS });
  }

  if (upstream.status === 404 || upstream.status === 413) {
    return new Response(null, { status: upstream.status, headers: SAFE_HEADERS });
  }
  if (upstream.status !== 200) {
    return new Response(null, { status: 502, headers: SAFE_HEADERS });
  }

  const mimeType = upstream.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase();
  const declaredSize = upstream.headers.get("content-length");
  if (!mimeType || !ALLOWED_TYPES.has(mimeType) || !declaredSize || !/^\d+$/.test(declaredSize)) {
    return new Response(null, { status: 502, headers: SAFE_HEADERS });
  }
  const expectedBytes = Number(declaredSize);
  if (!Number.isSafeInteger(expectedBytes) || expectedBytes < 0 || expectedBytes > MAX_ARTIFACT_BYTES) {
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
  } catch {
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

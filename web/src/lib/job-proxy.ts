import { API_BASE } from "@/lib/api";
import { isOpaqueDemoId } from "@/lib/demo";

const MAX_BODY_BYTES = 4096;
const MAX_REPLY_BYTES = 1024 * 1024;
const HEADERS = { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };
const FIELDS = ["strategy_id", "dataset_id", "window_id", "cost_profile_id", "idempotency_key"] as const;

function error(status: number, code: string, message: string): Response {
  return Response.json({ error: { code, message } }, { status, headers: HEADERS });
}

function localOrigin(request: Request): boolean {
  const host = request.headers.get("host");
  const origin = request.headers.get("origin");
  if (!host || !origin) return false;
  try {
    const hostUrl = new URL(`http://${host}`);
    const originUrl = new URL(origin);
    return hostUrl.host === host
      && ["localhost", "127.0.0.1", "[::1]"].includes(hostUrl.hostname.toLowerCase())
      && originUrl.protocol === "http:"
      && originUrl.origin === `http://${host}`;
  } catch { return false; }
}

async function boundedBytes(stream: ReadableStream<Uint8Array> | null, limit: number,
  oversized: () => Error): Promise<Uint8Array> {
  if (!stream) throw new Error("Missing JSON body");
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) { await reader.cancel(); throw oversized(); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength; }
  return body;
}

async function jsonBody(request: Request): Promise<unknown> {
  const length = request.headers.get("content-length");
  if (length && (!/^\d+$/.test(length) || Number(length) > MAX_BODY_BYTES)) throw new RangeError("body_too_large");
  const body = await boundedBytes(request.body, MAX_BODY_BYTES, () => new RangeError("body_too_large"));
  return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(body));
}

async function boundedReply(response: Response): Promise<unknown> {
  if (!response.body) throw new Error("Missing response body");
  const declared = response.headers.get("content-length");
  if (declared && (!/^\d+$/.test(declared) || Number(declared) > MAX_REPLY_BYTES)) throw new Error("Oversized reply");
  const body = await boundedBytes(response.body, MAX_REPLY_BYTES, () => new Error("Oversized reply"));
  return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(body));
}

async function upstreamPost(path: string, body: object): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/demo/v1${path}`, {
      method: "POST", cache: "no-store", redirect: "manual",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      signal: AbortSignal.timeout(30000),
    });
  } catch {
    return error(502, "demo_unavailable", "The local demo service is unavailable.");
  }
  if (![200, 202, 400, 404, 409, 411, 413, 415, 503].includes(response.status)
      || !response.headers.get("content-type")?.startsWith("application/json")) {
    return error(502, "demo_unavailable", "The local demo service returned an unexpected response.");
  }
  try {
    const payload = await boundedReply(response);
    const headers: Record<string, string> = { ...HEADERS };
    if (response.status === 202) {
      const status = (payload as { data?: { status?: { run_id?: unknown } } })?.data?.status;
      if (typeof status?.run_id !== "string" || !isOpaqueDemoId(status.run_id)) {
        throw new Error("Missing public run ID");
      }
      headers.Location = `/runs/${status.run_id}`;
    }
    return Response.json(payload, { status: response.status, headers });
  } catch {
    return error(502, "demo_unavailable", "The local demo service returned an invalid response.");
  }
}

export async function submitJob(request: Request): Promise<Response> {
  if (!localOrigin(request)) return error(403, "forbidden_origin", "Use the local dashboard origin.");
  if (!request.headers.get("content-type")?.startsWith("application/json")) {
    return error(415, "unsupported_media_type", "Run requests must be JSON.");
  }
  let body: unknown;
  try { body = await jsonBody(request); }
  catch (exc) { return exc instanceof RangeError
    ? error(413, "request_too_large", "The run request exceeds 4 KB.")
    : error(400, "invalid_request", "The run request is not valid JSON."); }
  if (typeof body !== "object" || body === null || Array.isArray(body)
      || Object.keys(body).length !== FIELDS.length
      || !FIELDS.every((field) => typeof (body as Record<string, unknown>)[field] === "string")) {
    return error(400, "invalid_request", "Select approved run choices only.");
  }
  return upstreamPost("/runs", body);
}

export async function cancelJob(request: Request, runId: string): Promise<Response> {
  if (!localOrigin(request)) return error(403, "forbidden_origin", "Use the local dashboard origin.");
  if (!isOpaqueDemoId(runId)) return error(404, "not_found", "No run with this ID.");
  if (!request.headers.get("content-type")?.startsWith("application/json")) {
    return error(415, "unsupported_media_type", "Cancel requests must be JSON.");
  }
  let body: unknown;
  try { body = await jsonBody(request); }
  catch (exc) { return exc instanceof RangeError
    ? error(413, "request_too_large", "The cancel request exceeds 4 KB.")
    : error(400, "invalid_request", "The cancel request is not valid JSON."); }
  if (typeof body !== "object" || body === null || Array.isArray(body) || Object.keys(body).length) {
    return error(400, "invalid_request", "Cancel requests use an empty JSON object.");
  }
  return upstreamPost(`/runs/${runId}/cancel`, {});
}

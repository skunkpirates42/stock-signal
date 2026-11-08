import { API_BASE } from "@/lib/backend";
import { readOperationalStatus } from "@/lib/health";
import { failureCategory, recordFailure, RequestFailure } from "@/lib/failures";

async function fetchStatus() {
  try {
    return await fetch(`${API_BASE}/api/status`, {
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
  } catch (error) {
    const category = failureCategory(error);
    throw new RequestFailure(category === "unexpected" ? "transport" : category);
  }
}

export async function GET() {
  try {
    const response = await fetchStatus();
    if (!response.ok) throw new RequestFailure("http");
    const status = readOperationalStatus(await response.json(), "status");
    return Response.json(status, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    recordFailure("operational-status", error);
    return Response.json(
      { error: "Status update unavailable" },
      {
        status: 503,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
}

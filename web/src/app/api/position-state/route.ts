import { API_BASE } from "@/lib/api";
import { logUpstreamError, logUpstreamStatus } from "@/lib/log";

const POSITION_STATE_PATH = "/api/position-state";

export async function GET() {
  try {
    const response = await fetch(`${API_BASE}${POSITION_STATE_PATH}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) {
      logUpstreamStatus(POSITION_STATE_PATH, response.status);
      return positionStateUnavailable();
    }
    return Response.json(await response.json(), { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    logUpstreamError(POSITION_STATE_PATH, error);
    return positionStateUnavailable();
  }
}

function positionStateUnavailable(): Response {
  return Response.json(
    { error: "Position state unavailable" },
    {
      status: 503,
      headers: { "Cache-Control": "no-store" },
    },
  );
}

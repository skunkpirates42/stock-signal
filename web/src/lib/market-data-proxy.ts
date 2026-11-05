import { API_BASE } from "@/lib/api";
import { logUpstreamError, logUpstreamStatus } from "@/lib/log";

/** Fixed read-only endpoints; browser input cannot choose the upstream URL. */
export async function proxyMarketData(path: "/api/position-prices" | "/api/market-status") {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) {
      logUpstreamStatus(path, response.status);
      return marketDataUnavailable();
    }
    return Response.json(await response.json(), { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    logUpstreamError(path, error);
    return marketDataUnavailable();
  }
}

function marketDataUnavailable(): Response {
  return Response.json({ error: "Market data unavailable" }, { status: 503 });
}

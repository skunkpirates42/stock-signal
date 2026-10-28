import { API_BASE } from "@/lib/api";

export async function GET() {
  try {
    const response = await fetch(`${API_BASE}/api/position-prices`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!response.ok) throw new Error("Price service unavailable");
    return Response.json(await response.json(), { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "Prices unavailable" }, { status: 503 });
  }
}

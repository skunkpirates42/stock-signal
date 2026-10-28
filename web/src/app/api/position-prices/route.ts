import { proxyMarketData } from "@/lib/market-data-proxy";

export async function GET() {
  return proxyMarketData("/api/position-prices");
}

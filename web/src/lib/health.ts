export function heartbeatState(timestamp: string, now: number): "fresh" | "stale" {
  const age = now - Date.parse(timestamp);
  return Number.isFinite(age) && age >= -5000 && age <= 30000 ? "fresh" : "stale";
}

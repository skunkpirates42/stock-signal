import { formatCurrency, formatPrice } from "@/lib/format";

const UNSIGNED_AMOUNT_METRICS = new Set([
  "recorded_costs",
  "realized_max_drawdown",
  "marked_max_drawdown",
  "max_gross_exposure",
  "borrow_cost",
  "spread_cost",
  "slippage_cost",
  "fees",
]);

export function formatMetricAmount(name: string, value: number): string {
  return UNSIGNED_AMOUNT_METRICS.has(name) ? formatPrice(value) : formatCurrency(value);
}

export function averageOrNull(count: number, average: number): number | null {
  return count > 0 ? average : null;
}

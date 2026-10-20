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

export function isUnsignedAmount(name: string): boolean {
  return UNSIGNED_AMOUNT_METRICS.has(name);
}

export function formatMetricAmount(name: string, value: number): string {
  return isUnsignedAmount(name) ? formatPrice(value) : formatCurrency(value);
}

export function observedOrNull(count: number, value: number): number | null {
  return count > 0 ? value : null;
}

const DASH = "—";

export function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  const abs = Math.abs(value).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (value === 0) return `$${abs}`;
  return `${value > 0 ? "+" : "-"}$${abs}`;
}

export function formatPercent(fraction: number | null | undefined): string {
  if (fraction === null || fraction === undefined) return DASH;
  return `${(fraction * 100).toFixed(1)}%`;
}

export function formatR(value: number | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  return `${value >= 0 ? "+" : "-"}${Math.abs(value).toFixed(2)}R`;
}

export function formatTimestamp(raw: string | null | undefined): string {
  if (!raw) return DASH;
  if (raw === "start") return raw;
  return raw.replace("T", " ").slice(0, 16);
}

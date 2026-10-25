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

export function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  const abs = Math.abs(value).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `$${abs}`;
}

export function formatWholeDollars(value: number | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  return `$${Math.round(Math.abs(value)).toLocaleString("en-US")}`;
}

export function labelFromKey(key: string): string {
  return key.replaceAll("_", " ");
}

export type Tone = "positive" | "negative" | "muted";

export function toneForSign(value: number | null | undefined): Tone {
  if (value === null || value === undefined || value === 0) return "muted";
  return value > 0 ? "positive" : "negative";
}

export function formatRatio(value: number | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  return value.toFixed(2);
}

export function formatMultiplier(value: number): string {
  return value.toFixed(1);
}

export function formatPercent(fraction: number | null | undefined): string {
  if (fraction === null || fraction === undefined) return DASH;
  return `${(fraction * 100).toFixed(1)}%`;
}

export function formatR(value: number | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  return `${value >= 0 ? "+" : "-"}${Math.abs(value).toFixed(2)}R`;
}

export function formatDate(raw: string | null | undefined): string {
  if (!raw) return DASH;
  if (raw === "start") return raw;
  return raw.slice(0, 10);
}

export function formatTimestamp(raw: string | null | undefined): string {
  if (!raw) return DASH;
  if (raw === "start") return raw;
  return `${raw.replace("T", " ").slice(0, 16)} UTC`;
}

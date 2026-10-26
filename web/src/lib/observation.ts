import type { Metric } from "@/lib/demo";
import { toneForSign, type Tone } from "@/lib/format";
import { formatMetricAmount, isUnsignedAmount } from "@/lib/metrics";

export interface ObservedValue {
  text: string;
  tone: Tone;
  reason: string | null;
}

function amountTone(name: string, value: number): Tone {
  return isUnsignedAmount(name) ? "muted" : toneForSign(value);
}

export function describeObservation(name: string, metric: Metric | undefined): ObservedValue {
  if (!metric) return { text: "Unavailable", tone: "muted", reason: "No saved metric." };
  const { observation, unit } = metric;
  if (observation.availability !== "available")
    return { text: "Unavailable", tone: "muted", reason: observation.detail };
  const value = observation.value;
  if (unit === "USD")
    return { text: formatMetricAmount(name, value), tone: amountTone(name, value), reason: null };
  if (unit === "USD/session")
    return {
      text: `${formatMetricAmount(name, value)}/session`,
      tone: amountTone(name, value),
      reason: null,
    };
  if (unit === "count") return { text: String(value), tone: "muted", reason: null };
  return { text: `${value} ${unit}`, tone: "muted", reason: null };
}

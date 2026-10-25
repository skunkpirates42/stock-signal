import type { ObservedValue } from "@/lib/observation";

export default function AvailableValue({ text, tone, reason }: ObservedValue) {
  const value = <span className={tone === "muted" ? undefined : `tone-${tone}`}>{text}</span>;
  if (!reason) return value;
  return <>{value}<span className="value-reason">{reason}</span></>;
}

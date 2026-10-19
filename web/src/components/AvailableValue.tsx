import type { ObservedValue } from "@/lib/observation";

export default function AvailableValue({ text, tone, reason }: ObservedValue) {
  return <span className={tone === "muted" ? undefined : `tone-${tone}`} title={reason ?? undefined}>{text}</span>;
}

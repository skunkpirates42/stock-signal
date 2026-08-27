// Where entry sits on the stop-to-target axis, as a fraction. Works for both directions:
// a SHORT has its target below its stop, which flips the sign of numerator and
// denominator together. Deliberately unclamped — a fraction outside 0..1 means a
// malformed level set, and clamping here would hide that from the caller.
export type EntryLabelAnchor = "start" | "middle" | "end";

// Near the ends of the track a centred label would hang off the card, so the entry
// label anchors to the marker's near edge instead of straddling it.
export function entryLabelAnchor(offset: number): EntryLabelAnchor {
  if (offset < 0.1) return "start";
  if (offset > 0.9) return "end";
  return "middle";
}

export function entryFraction(stop: number, entry: number, target: number): number | null {
  const span = target - stop;
  if (span === 0) return null;
  const fraction = (entry - stop) / span;
  return Number.isFinite(fraction) ? fraction : null;
}

// Where entry sits on the stop-to-target axis, as a fraction. Works for both directions:
// a SHORT has its target below its stop, which flips the sign of numerator and
// denominator together. Deliberately unclamped — a fraction outside 0..1 means a
// malformed level set, and clamping here would hide that from the caller.
export function entryFraction(stop: number, entry: number, target: number): number | null {
  const span = target - stop;
  if (span === 0) return null;
  const fraction = (entry - stop) / span;
  return Number.isFinite(fraction) ? fraction : null;
}

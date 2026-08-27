export function shareOfMax(values: number[]): number[] {
  const largest = Math.max(0, ...values.map((value) => Math.abs(value)));
  return values.map((value) => (largest === 0 ? 0 : Math.abs(value) / largest));
}

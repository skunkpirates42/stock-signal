export const PROVISIONAL_FLOOR = 50;

export function isProvisional(nClosed: number): boolean {
  return nClosed < PROVISIONAL_FLOOR;
}

export function sampleWarning(source: "live" | "all", nClosed: number, nLiveClosed: number): string | null {
  const floor = `The project's evaluation floor is ${PROVISIONAL_FLOOR} closed trades`;
  if (source === "live") {
    if (nClosed === 0) return `No live trades have closed yet. ${floor}.`;
    if (!isProvisional(nClosed)) return null;
    const trades = nClosed === 1 ? "trade" : "trades";
    return `Provisional: only ${nClosed} closed ${trades}. ${floor} — no conclusion should be drawn from this sample yet.`;
  }
  if (nClosed === 0) return null;
  if (nLiveClosed === 0) {
    return `None of these ${nClosed} closed trades are live. They are all backtest replay of a different period, not a live track record.`;
  }
  return `Only ${nLiveClosed} of these ${nClosed} closed trades are live; the other ${nClosed - nLiveClosed} are backtest replay `
    + "of a different period. These blended figures are not a live track record — switch to the live-only view above for the real sample.";
}

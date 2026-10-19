export const DEFAULT_COST_PER_TRADE = 2.0;

export function netExpectancy(grossExpectancy: number | null, costPerTrade: number): number | null {
  return grossExpectancy === null ? null : grossExpectancy - costPerTrade;
}

// The cost per trade at which net expectancy reaches zero. An edge that is already at or
// below zero has no such crossing, so it reports zero rather than a negative cost.
export function breakEvenCost(grossExpectancy: number | null): number {
  return grossExpectancy !== null && grossExpectancy > 0 ? grossExpectancy : 0;
}

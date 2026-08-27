export const DEFAULT_COST_PER_TRADE = 2.0;

export function netExpectancy(grossExpectancy: number, costPerTrade: number): number {
  return grossExpectancy - costPerTrade;
}

// The cost per trade at which net expectancy reaches zero. An edge that is already at or
// below zero has no such crossing, so it reports zero rather than a negative cost.
export function breakEvenCost(grossExpectancy: number): number {
  return grossExpectancy > 0 ? grossExpectancy : 0;
}

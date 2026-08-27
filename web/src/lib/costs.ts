export const DEFAULT_COST_PER_TRADE = 2.0;

export function netExpectancy(grossExpectancy: number, costPerTrade: number): number {
  return grossExpectancy - costPerTrade;
}

export const PROVISIONAL_FLOOR = 50;

export function isProvisional(nClosed: number): boolean {
  return nClosed < PROVISIONAL_FLOOR;
}

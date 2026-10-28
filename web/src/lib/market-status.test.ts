import { expect, it } from "vitest";
import { marketStatusLabel } from "./health";

const checked_at = "2026-10-28T15:00:00Z";
const now = Date.parse(checked_at);
it("distinguishes the regular market clock from unavailable or stale data", () => {
  expect(marketStatusLabel({ market_open: true, checked_at }, now)).toBe("US regular market: open");
  expect(marketStatusLabel({ market_open: false, checked_at }, now)).toBe(
    "US regular market: closed",
  );
  expect(marketStatusLabel({ market_open: null, checked_at }, now)).toContain("unavailable");
  expect(marketStatusLabel(null, now)).toContain("unavailable");
  expect(marketStatusLabel({ market_open: true, checked_at }, now + 61000)).toContain(
    "unavailable",
  );
});

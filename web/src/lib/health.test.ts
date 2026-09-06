import { expect, it } from "vitest";
import { heartbeatState } from "./health";
it("distinguishes API availability from old or invalid worker heartbeats", () => {
  const now = Date.parse("2026-06-10T14:00:00Z");
  expect(heartbeatState("2026-06-10T13:59:50Z", now)).toBe("fresh");
  expect(heartbeatState("2026-06-10T13:00:00Z", now)).toBe("stale");
  expect(heartbeatState("invalid", now)).toBe("stale");
});

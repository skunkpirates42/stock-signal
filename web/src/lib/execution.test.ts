import { expect, it } from "vitest";
import { observationFresh, provenance } from "./execution";
import type { Trade } from "./types";
it("expires observations independently of fetches or prices", () => {
  const now = new Date("2026-10-29T14:00:31Z");
  expect(observationFresh("2026-10-29T14:00:00Z", now)).toBe(false);
  expect(observationFresh("2026-10-29T14:00:01Z", now)).toBe(true);
  expect(observationFresh(null, now)).toBe(false);
  expect(observationFresh("bad", now)).toBe(false);
  expect(observationFresh("2026-10-29T14:01:00Z", now)).toBe(false);
});
it("does not infer broker ownership from live source", () => {
  const trade = { source: "live" } as Trade;
  expect(provenance(trade)).toBe("Unknown provenance");
  expect(provenance({ ...trade, backend: "local", account: "a" })).toBe("Local simulation");
  expect(provenance({ ...trade, backend: "alpaca", account: "a" })).toBe("Alpaca paper");
  expect(provenance({ ...trade, backend: "alpaca", account: "a", source: "backtest" })).toBe(
    "Replay",
  );
});

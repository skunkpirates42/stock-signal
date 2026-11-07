import { describe, expect, it } from "vitest";
import { parseSignalQuery, signalQueryParams, signalSearchHref } from "./signalSearch";

describe("signal search URLs", () => {
  it("defaults to live, non-WAIT signals on the first page", () => {
    const query = parseSignalQuery({});
    expect(query).toMatchObject({ source: "live", hideWait: true, page: 1 });
    expect(signalSearchHref(query)).toBe("/signals");
  });

  it("round trips every filter and the pagination snapshot for refresh and sharing", () => {
    const params = {
      source: "all",
      ticker: "SPY",
      direction: "SHORT",
      min_confidence: "0.85",
      from: "2026-06-01",
      to: "2026-06-30",
      include_wait: "true",
      page: "12",
      snapshot_id: "801",
    };
    expect(Object.fromEntries(signalQueryParams(parseSignalQuery(params)))).toEqual(params);
  });

  it.each([
    { source: "unknown" },
    { source: ["live", "all"] },
    { direction: "BUY" },
    { min_confidence: "NaN" },
    { min_confidence: "" },
    { min_confidence: "1.1" },
    { from: "2026-02-30" },
    { from: "2026-06-11", to: "2026-06-10" },
    { include_wait: "yes" },
    { page: "0" },
    { page: "2147483648" },
    { page: "1.5" },
    { snapshot_id: "-1" },
    { snapshot_id: "9007199254740992" },
  ])("rejects invalid filters instead of silently widening a search: %o", (params) => {
    expect(() => parseSignalQuery(params)).toThrow();
  });

  it("allows the maximum calendar date", () => {
    expect(parseSignalQuery({ to: "9999-12-31" }).to).toBe("9999-12-31");
  });
});

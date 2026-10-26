import { describe, expect, it } from "vitest";
import { closedDateRange, dateRangeQuery } from "@/lib/dateRange";

describe("closedDateRange", () => {
  it("keeps valid YYYY-MM-DD bounds", () => {
    expect(closedDateRange({ from: "2026-03-01", to: "2026-03-31" })).toEqual({
      from: "2026-03-01",
      to: "2026-03-31",
    });
  });

  it("drops malformed or impossible dates instead of failing the page", () => {
    expect(closedDateRange({ from: "03/01/2026", to: "2026-13-40" })).toEqual({});
  });

  it("drops empty bounds left by a cleared date input", () => {
    expect(closedDateRange({ from: "", to: "2026-03-31" })).toEqual({ to: "2026-03-31" });
  });
});

describe("dateRangeQuery", () => {
  it("adds only the bounds that are set", () => {
    expect(dateRangeQuery({ to: "2026-03-31" }).toString()).toBe("to=2026-03-31");
    expect(dateRangeQuery({}).toString()).toBe("");
  });
});

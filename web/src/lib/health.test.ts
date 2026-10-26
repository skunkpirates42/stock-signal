import { describe, expect, it } from "vitest";
import { describeStatus, heartbeatState, type OperationalStatus } from "./health";
it("distinguishes API availability from old or invalid worker heartbeats", () => {
  const now = Date.parse("2026-06-10T14:00:00Z");
  expect(heartbeatState("2026-06-10T13:59:50Z", now)).toBe("fresh");
  expect(heartbeatState("2026-06-10T13:00:00Z", now)).toBe("stale");
  expect(heartbeatState("invalid", now)).toBe("stale");
});

describe("describeStatus", () => {
  const checkedAt = "2026-06-10T14:00:00Z";
  const row = (scope: string, updated_at: string) => ({
    scope,
    status: "running",
    updated_at,
    detail: "ok",
    data_at: null,
  });
  const order = {
    id: "o1",
    ticker: "AAPL",
    purpose: "entry",
    state: "submitted",
    filled_qty: 0,
    requested_qty: 10,
  };
  const status = (overrides: Partial<OperationalStatus> = {}): OperationalStatus => ({
    latest_bar: null,
    runtime: [row("live:worker", "2026-06-10T13:59:50Z")],
    unresolved_orders: [],
    ...overrides,
  });

  it("labels the scope from the source parameter", () => {
    expect(
      describeStatus({ source: null, status: null, apiFailed: false, checkedAt: null }).scope,
    ).toBe("Live");
    expect(
      describeStatus({ source: "live", status: null, apiFailed: false, checkedAt: null }).scope,
    ).toBe("Live");
    expect(
      describeStatus({ source: "all", status: null, apiFailed: false, checkedAt: null }).scope,
    ).toBe("All sources");
  });

  it("keeps the heartbeat unknown until the API has answered", () => {
    const summary = describeStatus({
      source: null,
      status: null,
      apiFailed: false,
      checkedAt: null,
    });
    expect(summary.api).toBe("checking");
    expect(summary.heartbeat).toBe("unknown");
    expect(summary.latestBar).toBeNull();
  });

  it("reports a healthy API with a fresh heartbeat", () => {
    const summary = describeStatus({ source: null, status: status(), apiFailed: false, checkedAt });
    expect(summary.api).toBe("ok");
    expect(summary.heartbeat).toBe("fresh");
    expect(summary.runtime.map((r) => r.heartbeat)).toEqual(["fresh"]);
  });

  it("reports stale when any runtime row is stale", () => {
    const runtime = [
      row("live:worker", "2026-06-10T13:59:50Z"),
      row("live:stream", "2026-06-10T13:00:00Z"),
    ];
    const summary = describeStatus({
      source: null,
      status: status({ runtime }),
      apiFailed: false,
      checkedAt,
    });
    expect(summary.heartbeat).toBe("stale");
    expect(summary.runtime.map((r) => r.heartbeat)).toEqual(["fresh", "stale"]);
  });

  it("reports none when no runtime heartbeat is recorded", () => {
    expect(
      describeStatus({ source: null, status: status({ runtime: [] }), apiFailed: false, checkedAt })
        .heartbeat,
    ).toBe("none");
  });

  it("does not vouch for a heartbeat while the API is unavailable, but keeps last known rows and orders", () => {
    const summary = describeStatus({
      source: null,
      status: status({ unresolved_orders: [order] }),
      apiFailed: true,
      checkedAt,
    });
    expect(summary.api).toBe("unavailable");
    expect(summary.heartbeat).toBe("unknown");
    expect(summary.runtime).toHaveLength(1);
    expect(summary.unresolvedOrders).toEqual([order]);
  });
});

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import PositionExecution from "./PositionExecution";
import type { ExecutionPosition } from "@/lib/execution";

const now = new Date("2026-10-29T14:00:00Z");
const position: ExecutionPosition = {
  provenance: "Alpaca paper",
  signal_id: null,
  direction: "LONG",
  entry: 100,
  shares: 10,
  exit_price: null,
  outcome: "OPEN",
  pnl: null,
  entry_bar: null,
  exit_bar: null,
  bars_held: null,
  created_at: now.toISOString(),
  closed_at: null,
  source: "live",
  backend: "alpaca",
  id: 1,
  ticker: "SPY",
  account: "a",
  stop: 95,
  target: 110,
  remaining_shares: 10,
  execution: {
    entry: null,
    protection: "confirmed",
    pending_exit: null,
    legs: {
      stop: {
        state: "new",
        coverage: true,
        current: true,
        quantity: 10,
        updated_at: now.toISOString(),
      },
      target: {
        state: "accepted",
        coverage: true,
        current: true,
        quantity: 10,
        updated_at: now.toISOString(),
      },
    },
  },
};
const render = (at: Date, current = true, value = position) =>
  renderToStaticMarkup(createElement(PositionExecution, { position: value, current, now: at }));
it("expires child confirmation without another fetch", () => {
  expect(render(now)).toContain("Protection confirmed at last observation");
  const expired = render(new Date(now.getTime() + 31000));
  expect(expired).toContain("Warning: current protection is not confirmed");
  expect(expired).toContain("observation stale/unknown");
  expect(render(now, false)).not.toContain("Protection confirmed at last observation");
});
it("labels held protection and pending session close", () => {
  const held: ExecutionPosition = {
    ...position,
    execution: {
      ...position.execution!,
      protection: "unconfirmed",
      pending_exit: "session_close",
      legs: { stop: { ...position.execution!.legs.stop, state: "held" } },
    },
  };
  const html = render(now, true, held);
  expect(html).toContain("awaiting activation; not confirmed active");
  expect(html).toContain("Pending exit: session_close");
  expect(html).toContain("Warning: current protection is not confirmed");
});

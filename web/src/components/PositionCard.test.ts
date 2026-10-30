import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import PositionCard from "./PositionCard";
import type { Trade } from "@/lib/types";

const position: Trade = {
  id: 1,
  signal_id: null,
  ticker: "SPY",
  direction: "LONG",
  entry: 100,
  stop: 95,
  target: 110,
  shares: 10,
  remaining_shares: 4,
  exit_price: null,
  outcome: "OPEN",
  pnl: null,
  entry_bar: null,
  exit_bar: null,
  bars_held: null,
  created_at: "2026-10-28T15:00:00Z",
  closed_at: null,
  source: "live",
};
it("labels stale estimates and renders the price marker", () => {
  const html = renderToStaticMarkup(
    createElement(PositionCard, {
      position,
      stale: false,
      mark: { price: 103, timestamp: position.created_at },
      now: new Date("2026-10-28T15:05:00Z"),
    }),
  );
  expect(html).toContain("STALE PRICE");
  expect(html).toContain("Last known price");
  expect(html).toContain("$12.00");
  expect(html).toContain("level-scale-current");
  expect(html).toContain("(last price)");
});
it("shows missing prices honestly and leaves replay at entry", () => {
  const live = renderToStaticMarkup(createElement(PositionCard, { position, stale: false }));
  expect(live).toContain("Price unavailable");
  expect(live).toContain("(at entry)");
  const replay = renderToStaticMarkup(
    createElement(PositionCard, {
      position: { ...position, source: "backtest" },
      stale: false,
    }),
  );
  expect(replay).not.toContain("unrealized");
  expect(replay).not.toContain("level-scale-current");
  expect(replay).not.toContain("Live price");
});

it("shows the live price above the scale without duplicating it in the metrics", () => {
  const html = renderToStaticMarkup(
    createElement(PositionCard, {
      position,
      stale: false,
      mark: { price: 103, timestamp: position.created_at },
      now: new Date(position.created_at),
    }),
  );
  expect(html).toContain('Live price</dt><dd class="num">$103.00</dd>');
  expect(html.indexOf("Live price")).toBeLessThan(html.indexOf("level-scale"));
  expect(html).not.toContain(">Last price</dt>");
});

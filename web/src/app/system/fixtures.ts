import type { StatTileProps } from "@/components/StatTile";
import type { Metric } from "@/lib/demo";

export const COLOR_TOKENS = [
  "--ground",
  "--surface",
  "--surface-2",
  "--line",
  "--line-strong",
  "--ink",
  "--muted",
  "--faint",
  "--accent",
  "--caution",
  "--positive",
  "--negative",
];

export const TYPE_SCALE = [
  "--text-hero",
  "--text-title",
  "--text-stat",
  "--text-lead",
  "--text-body",
  "--text-small",
  "--text-label",
];

const savedUsd = (value: number): Metric => ({
  observation: { availability: "available", value, reason: null, detail: null },
  unit: "USD",
  basis: "Fixture",
  source_pointer: null,
});

export const OBSERVATIONS: { state: string; name: string; metric: Metric | undefined }[] = [
  { state: "Available, profit", name: "realized_net_pnl", metric: savedUsd(2220.33) },
  { state: "Available, loss", name: "marked_net_pnl", metric: savedUsd(-12.5) },
  { state: "Available, unsigned amount", name: "realized_max_drawdown", metric: savedUsd(3856.8) },
  {
    state: "Available, count",
    name: "closed_trades",
    metric: { ...savedUsd(2734), unit: "count" },
  },
  { state: "Available, zero", name: "realized_net_pnl", metric: savedUsd(0) },
  {
    state: "Unavailable",
    name: "fees",
    metric: {
      observation: {
        availability: "unavailable",
        value: null,
        reason: "not_recorded",
        detail: "Fees were not saved.",
      },
      unit: "USD",
      basis: "Fixture",
      source_pointer: null,
    },
  },
  { state: "Missing from the result", name: "borrow_cost", metric: undefined },
];

export const STAT_TILES: StatTileProps[] = [
  { label: "Positive", value: "$2,220.33", tone: "positive" },
  { label: "Negative", value: "-$12.50", tone: "negative" },
  { label: "Muted", value: "2734" },
  { label: "With note", value: "$3,881.57", note: "Marked to latest close" },
  { label: "Unavailable", value: "Unavailable", note: "No saved metric." },
];

export const TABLE_ROWS = [
  { symbol: "AAPL", trades: 412, pnl: 1840.12 },
  { symbol: "MSFT", trades: 388, pnl: -310.4 },
  { symbol: "NVDA", trades: 129, pnl: 0 },
];

import { beforeEach, describe, expect, it, vi } from "vitest";
import { Children, isValidElement, type ReactNode } from "react";
import type { Metrics } from "@/lib/types";

const metrics: Metrics = {
  n_closed: 0, n_open: 0, n_wins: 0, n_losses: 0, win_rate: 0, avg_win: 0, avg_loss: 0,
  expectancy: 0, profit_factor: null, total_pnl: 0, max_drawdown: 0, max_drawdown_pct: 0,
  avg_bars_held: 0, avg_r_multiple: 0, avg_win_r: 0, avg_loss_r: 0, by_ticker: {}, by_regime: {},
  starting_capital: 100000, ending_capital: 100000, equity: [],
};
const getMetrics = vi.fn(async (): Promise<Metrics> => metrics);
vi.mock("@/lib/api", () => ({ getMetrics: () => getMetrics() }));

import Page from "./page";

function valueOf(node: unknown, label: string): unknown {
  if (!isValidElement<{ label?: string; value?: unknown; children?: unknown }>(node)) return undefined;
  if (node.props.label === label) return node.props.value;
  for (const child of Children.toArray(node.props.children as ReactNode)) {
    const found = valueOf(child, label);
    if (found !== undefined) return found;
  }
  return undefined;
}

describe("overview", () => {
  beforeEach(() => getMetrics.mockResolvedValue(metrics));

  it("shows dashes, not zeros, for P&L and drawdown before any trade closes", async () => {
    const page = await Page({ searchParams: Promise.resolve({}) });
    expect(valueOf(page, "Closed-trade net P&L")).toBe("—");
    expect(valueOf(page, "Max drawdown")).toBe("—");
  });

  it("keeps real figures once trades have closed, including a real zero", async () => {
    getMetrics.mockResolvedValue({ ...metrics, n_closed: 3, total_pnl: 0, max_drawdown: 120.5, max_drawdown_pct: 0.012 });
    const page = await Page({ searchParams: Promise.resolve({}) });
    expect(valueOf(page, "Closed-trade net P&L")).toBe("$0.00");
    expect(valueOf(page, "Max drawdown")).toBe("$120.50 (1.2%)");
  });
});

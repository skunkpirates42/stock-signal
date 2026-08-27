"use client";

import { useState } from "react";
import { DEFAULT_COST_PER_TRADE, netExpectancy } from "@/lib/costs";
import { formatCurrency } from "@/lib/format";

export interface CostAdjustedExpectancyProps {
  grossExpectancy: number;
}

export default function CostAdjustedExpectancy({ grossExpectancy }: CostAdjustedExpectancyProps) {
  const [costPerTrade, setCostPerTrade] = useState(DEFAULT_COST_PER_TRADE);
  const net = netExpectancy(grossExpectancy, costPerTrade);

  return (
    <div className="cost-adjusted-expectancy">
      <h2>Cost-adjusted expectancy</h2>
      <div className="cost-adjusted-row">
        <div className="cost-adjusted-stat">
          <div className="stat-tile-label">Gross</div>
          <div className={`stat-tile-value stat-tile-value-${grossExpectancy >= 0 ? "positive" : "negative"}`}>
            {formatCurrency(grossExpectancy)}
          </div>
        </div>
        <div className="cost-adjusted-stat">
          <div className="stat-tile-label">Net</div>
          <div className={`stat-tile-value stat-tile-value-${net >= 0 ? "positive" : "negative"}`}>
            {formatCurrency(net)}
          </div>
        </div>
        <label className="cost-adjusted-input">
          Cost per trade
          <input
            type="number"
            step="0.25"
            min="0"
            value={costPerTrade}
            onChange={(e) => setCostPerTrade(Number(e.target.value))}
          />
        </label>
      </div>
      <p className="cost-adjusted-note">
        Backtest analysis found the strategy&apos;s edge sits below realistic transaction
        costs. Adjust the cost input to see where net expectancy crosses zero.
      </p>
    </div>
  );
}

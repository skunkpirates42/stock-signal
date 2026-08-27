"use client";

import { useState } from "react";
import { DEFAULT_COST_PER_TRADE, breakEvenCost, netExpectancy } from "@/lib/costs";
import { formatCurrency, formatPrice } from "@/lib/format";

export interface CostAdjustedExpectancyProps {
  grossExpectancy: number;
}

export default function CostAdjustedExpectancy({ grossExpectancy }: CostAdjustedExpectancyProps) {
  const [costPerTrade, setCostPerTrade] = useState(DEFAULT_COST_PER_TRADE);
  const net = netExpectancy(grossExpectancy, costPerTrade);
  const breakEven = breakEvenCost(grossExpectancy);

  return (
    <div className="cost-adjusted-expectancy">
      <h2 className="micro">Cost-adjusted expectancy</h2>
      <div className="cost-adjusted-row">
        <div className="cost-adjusted-stat">
          <div className="stat-tile-label">Gross</div>
          <div className={`stat-tile-value ${grossExpectancy >= 0 ? "tone-positive" : "tone-negative"}`}>
            {formatCurrency(grossExpectancy)}
          </div>
        </div>
        <div className="cost-adjusted-stat">
          <div className="stat-tile-label">Net</div>
          <div className={`stat-tile-value ${net >= 0 ? "tone-positive" : "tone-negative"}`}>
            {formatCurrency(net)}
          </div>
        </div>
        <div className="cost-adjusted-stat">
          <div className="micro">Breaks even at</div>
          <div className="num card-figure-sm">
            {breakEven > 0 ? `${formatPrice(breakEven)}/trade` : "—"}
          </div>
        </div>
        <label className="cost-adjusted-input">
          Cost per trade
          <input
            type="number"
            step="0.25"
            min="0"
            value={costPerTrade}
            onChange={(e) => setCostPerTrade(Number(e.target.value) || 0)}
          />
        </label>
      </div>
      <p className="cost-adjusted-crossing">
        {breakEven > 0
          ? `Net expectancy reaches zero at ${formatPrice(breakEven)} of cost per trade. Above that, the edge is gone.`
          : "Gross expectancy is already at or below zero, so no cost level makes this profitable."}
      </p>
      <p className="cost-adjusted-note">
        Backtest analysis found the strategy&apos;s edge sits below realistic transaction
        costs. Adjust the cost input to see where net expectancy crosses zero.
      </p>
    </div>
  );
}

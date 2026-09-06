"use client";

import { useState } from "react";
import { DEFAULT_COST_PER_TRADE, breakEvenCost, netExpectancy } from "@/lib/costs";
import { formatCurrency, formatPrice } from "@/lib/format";

export interface CostAdjustedExpectancyProps {
  recordedExpectancy: number;
}

export default function CostAdjustedExpectancy({ recordedExpectancy }: CostAdjustedExpectancyProps) {
  const [costPerTrade, setCostPerTrade] = useState(DEFAULT_COST_PER_TRADE);
  const net = netExpectancy(recordedExpectancy, costPerTrade);
  const breakEven = breakEvenCost(recordedExpectancy);

  return (
    <div className="cost-adjusted-expectancy">
      <h2 className="micro">Cost-adjusted expectancy</h2>
      <div className="cost-adjusted-row">
        <div className="cost-adjusted-stat">
          <div className="stat-tile-label">Recorded net</div>
          <div className={`stat-tile-value ${recordedExpectancy >= 0 ? "tone-positive" : "tone-negative"}`}>
            {formatCurrency(recordedExpectancy)}
          </div>
        </div>
        <div className="cost-adjusted-stat">
          <div className="stat-tile-label">After extra cost</div>
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
          Additional cost per trade
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
          : "Recorded expectancy is already at or below zero, so no cost level makes this profitable."}
      </p>
      <p className="cost-adjusted-note">
        This is an additional hypothetical cost beyond costs already recorded. Legacy
        trades may have no modeled costs; broker fills already include execution spread.
      </p>
    </div>
  );
}

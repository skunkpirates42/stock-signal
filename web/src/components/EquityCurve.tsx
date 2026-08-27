"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { EquityPoint } from "@/lib/types";
import { formatCurrency, formatTimestamp } from "@/lib/format";

export interface EquityCurveProps {
  points: EquityPoint[];
}

export default function EquityCurve({ points }: EquityCurveProps) {
  if (points.length < 2) {
    return (
      <div className="equity-curve">
        <p className="equity-curve-empty">Not enough closed trades to plot</p>
      </div>
    );
  }

  return (
    <div className="equity-curve">
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={points} margin={{ top: 5, right: 20, bottom: 5, left: 5 }}>
          <defs>
            <linearGradient id="equity-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.28} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" />
          <XAxis dataKey="label" tickFormatter={formatTimestamp} stroke="var(--faint)" fontSize={11} />
          <YAxis domain={["auto", "auto"]} tickFormatter={formatCurrency} stroke="var(--faint)" fontSize={11} />
          <Tooltip
            labelFormatter={(label) => formatTimestamp(String(label))}
            formatter={(value) => formatCurrency(typeof value === "number" ? value : undefined)}
            contentStyle={{
              background: "var(--ground)",
              border: "1px solid var(--line-strong)",
              borderRadius: "var(--radius-sm)",
            }}
            labelStyle={{ color: "var(--muted)" }}
            itemStyle={{ color: "var(--ink)" }}
          />
          <Area type="monotone" dataKey="equity" stroke="var(--accent)" strokeWidth={2} fill="url(#equity-fill)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

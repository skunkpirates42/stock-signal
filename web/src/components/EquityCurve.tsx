"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
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
        <LineChart data={points} margin={{ top: 5, right: 20, bottom: 5, left: 5 }}>
          <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" />
          <XAxis dataKey="label" tickFormatter={formatTimestamp} stroke="var(--muted)" fontSize={12} />
          <YAxis domain={["auto", "auto"]} tickFormatter={formatCurrency} stroke="var(--muted)" fontSize={12} />
          <Tooltip
            labelFormatter={(label) => formatTimestamp(String(label))}
            formatter={(value) => formatCurrency(typeof value === "number" ? value : undefined)}
            contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)" }}
            labelStyle={{ color: "var(--fg)" }}
            itemStyle={{ color: "var(--fg)" }}
          />
          <Line type="monotone" dataKey="equity" stroke="var(--accent)" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

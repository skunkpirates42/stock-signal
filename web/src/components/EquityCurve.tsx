"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import Card from "@/components/Card";
import type { EquityPoint } from "@/lib/types";
import { formatDate, formatPrice, formatWholeDollars } from "@/lib/format";
import { summarizeEquityCurve } from "@/lib/equity";

export interface EquityCurveProps {
  points: EquityPoint[];
}

export default function EquityCurve({ points }: EquityCurveProps) {
  if (points.length < 2) {
    return (
      <Card title="Equity" titleVariant="label" className="equity-curve">
        <p className="equity-curve-empty">Not enough closed trades to plot</p>
      </Card>
    );
  }

  return (
    <Card title="Equity" titleVariant="label" className="equity-curve">
      <p className="sr-only">{summarizeEquityCurve(points)}</p>
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={points} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <defs>
            <linearGradient id="equity-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.28} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" />
          <XAxis dataKey="label" tickFormatter={formatDate} stroke="var(--faint)" fontSize={11} />
          <YAxis
            domain={["auto", "auto"]}
            tickFormatter={formatWholeDollars}
            width="auto"
            stroke="var(--faint)"
            fontSize={11}
          />
          <Tooltip
            labelFormatter={(label) => formatDate(String(label))}
            formatter={(value) => formatPrice(typeof value === "number" ? value : undefined)}
            contentStyle={{
              background: "var(--ground)",
              border: "1px solid var(--line-strong)",
              borderRadius: "var(--radius-sm)",
            }}
            labelStyle={{ color: "var(--muted)" }}
            itemStyle={{ color: "var(--ink)" }}
          />
          <Area
            type="monotone"
            dataKey="equity"
            stroke="var(--accent)"
            strokeWidth={2}
            fill="url(#equity-fill)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </Card>
  );
}

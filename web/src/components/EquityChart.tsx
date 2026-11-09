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
import type { EquityPoint } from "@/lib/types";
import { formatDate, formatBalance, formatWholeDollarBalance } from "@/lib/format";

export default function EquityChart({ points }: { points: EquityPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart
        data={points}
        accessibilityLayer
        aria-label="Equity over time"
        margin={{ top: 5, right: 20, bottom: 5, left: 0 }}
      >
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
          tickFormatter={formatWholeDollarBalance}
          width="auto"
          stroke="var(--faint)"
          fontSize={11}
        />
        <Tooltip
          labelFormatter={(label) => formatDate(String(label))}
          formatter={(value) => formatBalance(typeof value === "number" ? value : undefined)}
          isAnimationActive="auto"
          contentStyle={{
            background: "var(--ground)",
            border: "1px solid var(--line-strong)",
            borderRadius: "var(--radius-sm)",
          }}
          labelStyle={{ color: "var(--muted)" }}
          itemStyle={{ color: "var(--ink)" }}
        />
        <Area
          isAnimationActive="auto"
          type="monotone"
          dataKey="equity"
          stroke="var(--accent)"
          strokeWidth={2}
          fill="url(#equity-fill)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

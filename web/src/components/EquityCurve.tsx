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
import DataTable from "@/components/DataTable";
import Disclosure from "@/components/Disclosure";
import Card from "@/components/Card";
import type { EquityPoint } from "@/lib/types";
import { formatDate, formatBalance, formatTimestamp, formatWholeDollarBalance } from "@/lib/format";
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
      <p className="card-note">{summarizeEquityCurve(points)}</p>
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
      <Disclosure className="equity-data" summary="View equity data">
        <DataTable caption="Equity data">
          <thead>
            <tr>
              <th scope="col">Time (UTC)</th>
              <th scope="col" className="num">
                Equity
              </th>
            </tr>
          </thead>
          <tbody>
            {points.map((point, index) => (
              <tr key={`${point.label}-${index}`}>
                <td>{formatTimestamp(point.label)}</td>
                <td className="num">{formatBalance(point.equity)}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      </Disclosure>
    </Card>
  );
}

import type { Breakdown } from "@/lib/types";
import { formatCurrency, formatPercent } from "@/lib/format";

export interface BreakdownTableProps {
  title: string;
  rows: Record<string, Breakdown>;
}

export default function BreakdownTable({ title, rows }: BreakdownTableProps) {
  const sorted = Object.entries(rows).sort(([, a], [, b]) => b.pnl - a.pnl);

  return (
    <div className="breakdown-table">
      <h2>{title}</h2>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>N</th>
            <th>Win %</th>
            <th>P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map(([name, breakdown]) => (
            <tr key={name}>
              <td>{name}</td>
              <td>{breakdown.n}</td>
              <td>{formatPercent(breakdown.win_rate)}</td>
              <td className={breakdown.pnl >= 0 ? "positive" : "negative"}>
                {formatCurrency(breakdown.pnl)}
              </td>
            </tr>
          ))}
          {sorted.length === 0 && (
            <tr>
              <td colSpan={4} className="breakdown-empty">
                No rows.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

import type { Breakdown } from "@/lib/types";
import { breakdownRows } from "@/lib/breakdowns";
import { formatCurrency, formatPercent } from "@/lib/format";

export interface BreakdownTableProps {
  title: string;
  rows: Record<string, Breakdown>;
}

export default function BreakdownTable({ title, rows }: BreakdownTableProps) {
  const sorted = breakdownRows(rows);

  return (
    <section className="breakdown-table">
      <h2 className="micro">{title}</h2>
      <div className="table-scroll">
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
            {sorted.map((row) => (
              <tr key={row.name}>
                <td>{row.name}</td>
                <td className="num">{row.n}</td>
                <td className="num">{formatPercent(row.win_rate)}</td>
                <td className={`num ${row.pnl >= 0 ? "tone-positive" : "tone-negative"}`}>
                  <span className="cell-bar" style={{ width: `${row.share * 100}%` }} aria-hidden="true" />
                  <span className="cell-value">{formatCurrency(row.pnl)}</span>
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
    </section>
  );
}

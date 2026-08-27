import type { Trade } from "@/lib/types";
import { formatCurrency, formatPrice, formatTimestamp } from "@/lib/format";
import { shareOfMax } from "@/lib/scale";

export interface FillsTableProps {
  trades: Trade[];
}

function outcomeClass(outcome: Trade["outcome"]): string {
  if (outcome === "WIN") return "tone-positive";
  if (outcome === "LOSS") return "tone-negative";
  return "tone-muted";
}

export default function FillsTable({ trades }: FillsTableProps) {
  const sorted = [...trades].sort((a, b) => (b.closed_at ?? "").localeCompare(a.closed_at ?? ""));
  const shares = shareOfMax(sorted.map((trade) => trade.pnl ?? 0));

  return (
    <div className="fills-table">
      <h2>Recent fills</h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Direction</th>
              <th>Entry</th>
              <th>Exit</th>
              <th>Outcome</th>
              <th>P&amp;L</th>
              <th>Bars held</th>
              <th>Closed</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((trade, index) => (
              <tr key={trade.id}>
                <td>{trade.ticker}</td>
                <td>{trade.direction}</td>
                <td>{formatPrice(trade.entry)}</td>
                <td>{formatPrice(trade.exit_price)}</td>
                <td className={outcomeClass(trade.outcome)}>{trade.outcome}</td>
                <td className={`pnl-cell num ${trade.pnl !== null && trade.pnl >= 0 ? "tone-positive" : "tone-negative"}`}>
                  <span className="cell-bar" style={{ width: `${shares[index] * 100}%` }} aria-hidden="true" />
                  <span className="cell-value">{formatCurrency(trade.pnl)}</span>
                </td>
                <td>{trade.bars_held ?? "—"}</td>
                <td>{formatTimestamp(trade.closed_at)}</td>
              </tr>
            ))}
            {sorted.length === 0 && (
              <tr>
                <td colSpan={8} className="fills-empty">
                  No closed trades yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

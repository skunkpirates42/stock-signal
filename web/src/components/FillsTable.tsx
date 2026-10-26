import DataTable from "@/components/DataTable";
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
  const sorted = [...trades].sort((a, b) =>
    (b.exit_at ?? b.closed_at ?? "").localeCompare(a.exit_at ?? a.closed_at ?? ""),
  );
  const shares = shareOfMax(sorted.map((trade) => trade.pnl ?? 0));

  return (
    <div className="fills-table">
      <h2>Recent fills</h2>
      <DataTable>
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Direction</th>
            <th className="num">Entry</th>
            <th className="num">Exit</th>
            <th>Outcome</th>
            <th className="num">P&amp;L</th>
            <th className="num">Bars held</th>
            <th>Closed</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((trade, index) => (
            <tr key={trade.id}>
              <td>
                {trade.ticker}{" "}
                <small>
                  {trade.source ?? "unknown"} · {trade.backend ?? "unknown backend"}
                </small>
              </td>
              <td>{trade.direction}</td>
              <td className="num">{formatPrice(trade.entry)}</td>
              <td className="num">{formatPrice(trade.exit_price)}</td>
              <td className={outcomeClass(trade.outcome)}>{trade.outcome}</td>
              <td
                className={`pnl-cell num ${trade.pnl !== null && trade.pnl >= 0 ? "tone-positive" : "tone-negative"}`}
              >
                <span
                  className="cell-bar"
                  style={{ width: `${shares[index] * 100}%` }}
                  aria-hidden="true"
                />
                <span className="cell-value">{formatCurrency(trade.pnl)}</span>
              </td>
              <td className="num">{trade.bars_held ?? "—"}</td>
              <td>{formatTimestamp(trade.exit_at ?? trade.closed_at)}</td>
            </tr>
          ))}
          {sorted.length === 0 && (
            <tr>
              <td colSpan={8} className="data-table-empty">
                No closed trades yet.
              </td>
            </tr>
          )}
        </tbody>
      </DataTable>
    </div>
  );
}

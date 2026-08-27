import type { Trade } from "@/lib/types";
import { formatCurrency, formatTimestamp } from "@/lib/format";
import { distanceToStop, distanceToTarget, isStale } from "@/lib/positions";

export interface PositionsTableProps {
  positions: Trade[];
  now: Date;
}

function directionClass(direction: Trade["direction"]): string {
  return direction === "SHORT" ? "tone-negative" : "tone-positive";
}

export default function PositionsTable({ positions, now }: PositionsTableProps) {
  return (
    <div className="positions-table">
      <h2>Open positions</h2>
      <p className="positions-note">
        No live price feed is wired into this dashboard. The columns below show distance to
        stop and distance to target as of entry — not current value or unrealized P&amp;L,
        which this app has no data to compute.
      </p>
      <table>
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Direction</th>
            <th>Entry</th>
            <th>Stop</th>
            <th>Target</th>
            <th>Shares</th>
            <th>Opened</th>
            <th>Distance to stop</th>
            <th>Distance to target</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((position) => {
            const stopDistance = distanceToStop(position);
            const targetDistance = distanceToTarget(position);
            const stale = isStale(position.created_at, now);
            return (
              <tr key={position.id}>
                <td>
                  {position.ticker}
                  {stale && <span className="positions-stale-badge">STALE</span>}
                </td>
                <td className={directionClass(position.direction)}>{position.direction}</td>
                <td>{formatCurrency(position.entry)}</td>
                <td>{formatCurrency(position.stop)}</td>
                <td>{formatCurrency(position.target)}</td>
                <td>{position.shares}</td>
                <td>{formatTimestamp(position.created_at)}</td>
                <td>{formatCurrency(stopDistance.dollars)}</td>
                <td>{formatCurrency(targetDistance.dollars)}</td>
              </tr>
            );
          })}
          {positions.length === 0 && (
            <tr>
              <td colSpan={9} className="positions-empty">
                No open positions.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

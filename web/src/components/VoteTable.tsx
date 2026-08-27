import type { VoteRow } from "@/lib/types";

export interface VoteTableProps {
  rows: VoteRow[];
}

function voteClass(vote: VoteRow["vote"]): string {
  if (vote === "bull") return "tone-positive";
  if (vote === "bear") return "tone-negative";
  return "tone-muted";
}

export default function VoteTable({ rows }: VoteTableProps) {
  if (rows.length === 0) {
    return <p className="vote-table-empty">No indicator votes recorded for this signal.</p>;
  }

  return (
    <table className="vote-table">
      <thead>
        <tr>
          <th>Indicator</th>
          <th>Vote</th>
          <th>Detail</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.indicator}>
            <td>{row.label}</td>
            <td className={voteClass(row.vote)}>{row.vote}</td>
            <td className="vote-table-detail">{row.detail}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

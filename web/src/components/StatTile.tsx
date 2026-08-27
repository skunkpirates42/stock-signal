export interface StatTileProps {
  label: string;
  value: string;
  tone?: "positive" | "negative" | "neutral";
  note?: string;
}

export default function StatTile({ label, value, tone = "neutral", note }: StatTileProps) {
  return (
    <div className="stat-tile">
      <div className="stat-tile-label">{label}</div>
      <div className={`stat-tile-value stat-tile-value-${tone}`}>{value}</div>
      {note && <div className="stat-tile-note">{note}</div>}
    </div>
  );
}

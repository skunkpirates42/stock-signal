import type { Tone } from "@/lib/format";

export interface StatTileProps {
  label: string;
  value: string;
  tone?: Tone;
  note?: string;
}

export default function StatTile({ label, value, tone = "muted", note }: StatTileProps) {
  return (
    <div className="stat-tile">
      <div className="stat-tile-label">{label}</div>
      <div className={`stat-tile-value tone-${tone}`}>{value}</div>
      {note && <div className="stat-tile-note">{note}</div>}
    </div>
  );
}

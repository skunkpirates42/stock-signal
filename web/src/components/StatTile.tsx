export interface StatTileProps {
  label: string;
  value: string;
  tone?: "positive" | "negative" | "neutral";
  note?: string;
}

const TONE_CLASS = {
  positive: "tone-positive",
  negative: "tone-negative",
  neutral: "tone-muted",
} as const;

export default function StatTile({ label, value, tone = "neutral", note }: StatTileProps) {
  return (
    <div className="stat-tile">
      <div className="stat-tile-label">{label}</div>
      <div className={`stat-tile-value ${TONE_CLASS[tone]}`}>{value}</div>
      {note && <div className="stat-tile-note">{note}</div>}
    </div>
  );
}

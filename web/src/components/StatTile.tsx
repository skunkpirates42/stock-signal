import MetricTerm from "@/components/MetricTerm";
import type { Tone } from "@/lib/format";
import type { MetricDefinition } from "@/lib/metricDefinitions";

export interface StatTileProps {
  label: string;
  value: string;
  tone?: Tone;
  note?: string;
  definition?: MetricDefinition;
}

export default function StatTile({
  label,
  value,
  tone = "muted",
  note,
  definition,
}: StatTileProps) {
  return (
    <div className="stat-tile">
      <div className="stat-tile-label">{definition ? <MetricTerm {...definition} /> : label}</div>
      <div className={`stat-tile-value tone-${tone}`}>{value}</div>
      {note && <div className="stat-tile-note">{note}</div>}
    </div>
  );
}

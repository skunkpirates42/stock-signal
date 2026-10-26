import Card from "@/components/Card";
import MetricTerm from "@/components/MetricTerm";
import { formatR, toneForSign } from "@/lib/format";
import { METRIC_DEFINITIONS } from "@/lib/metricDefinitions";

export interface RMultipleCardProps {
  avgR: number | null;
  avgWinR: number | null;
  avgLossR: number | null;
}

export default function RMultipleCard({ avgR, avgWinR, avgLossR }: RMultipleCardProps) {
  return (
    <Card title={<MetricTerm {...METRIC_DEFINITIONS.rMultiple} />} titleVariant="label">
      <p className={`card-figure num tone-${toneForSign(avgR)}`}>{formatR(avgR)}</p>
      <dl className="pair-grid">
        <div>
          <dt className="micro">Avg win</dt>
          <dd className={`num tone-${toneForSign(avgWinR)}`}>{formatR(avgWinR)}</dd>
        </div>
        <div>
          <dt className="micro">Avg loss</dt>
          <dd className={`num tone-${toneForSign(avgLossR)}`}>{formatR(avgLossR)}</dd>
        </div>
      </dl>
      <p className="card-note">
        Realized R against the 2:1 reward-to-risk the engine targets at entry.
      </p>
    </Card>
  );
}

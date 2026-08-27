import { formatR } from "@/lib/format";

export interface RMultipleCardProps {
  avgR: number;
  avgWinR: number;
  avgLossR: number;
}

export default function RMultipleCard({ avgR, avgWinR, avgLossR }: RMultipleCardProps) {
  return (
    <section className="card">
      <h2 className="micro">R-multiples</h2>
      <p className={`card-figure num tone-${avgR >= 0 ? "positive" : "negative"}`}>{formatR(avgR)}</p>
      <dl className="pair-grid">
        <div>
          <dt className="micro">Avg win</dt>
          <dd className="num tone-positive">{formatR(avgWinR)}</dd>
        </div>
        <div>
          <dt className="micro">Avg loss</dt>
          <dd className="num tone-negative">{formatR(avgLossR)}</dd>
        </div>
      </dl>
      <p className="card-note">
        Realized R against the 2:1 reward-to-risk the engine targets at entry.
      </p>
    </section>
  );
}

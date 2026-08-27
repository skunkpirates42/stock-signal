import RatioBar from "@/components/RatioBar";
import { formatCurrency, formatPercent } from "@/lib/format";

export interface WinLossCardProps {
  nWins: number;
  nLosses: number;
  winRate: number;
  avgWin: number;
  avgLoss: number;
}

export default function WinLossCard({ nWins, nLosses, winRate, avgWin, avgLoss }: WinLossCardProps) {
  return (
    <section className="card">
      <h2 className="micro">Win / loss</h2>
      <p className="card-figure num">{formatPercent(winRate)}</p>
      <RatioBar left={nWins} right={nLosses} leftLabel="wins" rightLabel="losses" />
      <dl className="pair-grid">
        <div>
          <dt className="micro">Avg win</dt>
          <dd className="num tone-positive">{formatCurrency(avgWin)}</dd>
        </div>
        <div>
          <dt className="micro">Avg loss</dt>
          <dd className="num tone-negative">{formatCurrency(avgLoss)}</dd>
        </div>
      </dl>
    </section>
  );
}

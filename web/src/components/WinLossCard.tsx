import Card from "@/components/Card";
import RatioBar from "@/components/RatioBar";
import { formatCurrency, formatPercent, toneForSign } from "@/lib/format";

export interface WinLossCardProps {
  nWins: number;
  nLosses: number;
  nBreakeven?: number;
  winRate: number | null;
  avgWin: number | null;
  avgLoss: number | null;
}

export default function WinLossCard({ nWins, nLosses, nBreakeven = 0, winRate, avgWin, avgLoss }: WinLossCardProps) {
  return (
    <Card title="Win / loss" titleVariant="label">
      <p className="card-figure num">{formatPercent(winRate)}</p>
      <RatioBar left={nWins} right={nLosses} leftLabel="wins" rightLabel="losses" />
      {nBreakeven > 0 && <p className="note">{nBreakeven} breakeven trades included in win-rate denominator; excluded from win/loss bar.</p>}
      <dl className="pair-grid">
        <div>
          <dt className="micro">Avg win</dt>
          <dd className={`num tone-${toneForSign(avgWin)}`}>{formatCurrency(avgWin)}</dd>
        </div>
        <div>
          <dt className="micro">Avg loss</dt>
          <dd className={`num tone-${toneForSign(avgLoss)}`}>{formatCurrency(avgLoss)}</dd>
        </div>
      </dl>
    </Card>
  );
}

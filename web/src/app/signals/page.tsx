import { getSignals, getTrades } from "@/lib/api";
import type { Trade } from "@/lib/types";
import SignalList from "@/components/SignalList";

export default async function SignalsPage() {
  // Live volume today is 269 signals. Filtering client-side after a single fetch is the
  // right call at this scale; it stops being right somewhere around a few thousand rows,
  // at which point ticker/direction/confidence/date filtering belongs in the Flask query
  // instead of in the browser.
  const signals = await getSignals({ source: "live", limit: 500 });
  const trades = await getTrades({ source: "live", limit: 500 });

  const outcomeBySignalId: Record<number, Trade["outcome"]> = {};
  for (const trade of trades) {
    if (trade.signal_id !== null) {
      outcomeBySignalId[trade.signal_id] = trade.outcome;
    }
  }

  return (
    <main className="page-content">
      <h1>Signals</h1>
      <SignalList signals={signals} outcomeBySignalId={outcomeBySignalId} />
    </main>
  );
}

"use client";

import { useMemo, useState } from "react";
import type { Signal, Trade } from "@/lib/types";
import { filterSignals, type SignalCriteria } from "@/lib/filters";
import FilterBar from "@/components/FilterBar";
import SignalRow from "@/components/SignalRow";

export interface SignalListProps {
  signals: Signal[];
  outcomeBySignalId: Record<number, Trade["outcome"]>;
}

export default function SignalList({ signals, outcomeBySignalId }: SignalListProps) {
  const [criteria, setCriteria] = useState<SignalCriteria>({});
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const tickers = useMemo(
    () => Array.from(new Set(signals.map((s) => s.ticker))).sort(),
    [signals],
  );

  const filtered = useMemo(() => filterSignals(signals, criteria), [signals, criteria]);

  return (
    <div className="signal-list">
      <FilterBar criteria={criteria} tickers={tickers} onChange={setCriteria} />

      <p className="signal-list-count">
        Showing {filtered.length} of {signals.length}
      </p>

      <div className="signal-rows">
        {filtered.map((signal) => (
          <SignalRow
            key={signal.id}
            signal={signal}
            outcome={outcomeBySignalId[signal.id] ?? null}
            expanded={expandedId === signal.id}
            onToggle={() =>
              setExpandedId((current) => (current === signal.id ? null : signal.id))
            }
          />
        ))}
        {filtered.length === 0 && (
          <p className="signal-list-empty">No signals match these filters.</p>
        )}
      </div>
    </div>
  );
}

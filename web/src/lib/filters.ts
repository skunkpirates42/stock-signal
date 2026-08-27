import type { Direction, Signal } from "@/lib/types";

export interface SignalCriteria {
  ticker?: string;
  direction?: Direction;
  minConfidence?: number;
  from?: string;
  to?: string;
}

export function filterSignals(signals: Signal[], criteria: SignalCriteria): Signal[] {
  return signals.filter((s) => {
    if (criteria.ticker && s.ticker !== criteria.ticker) return false;
    if (criteria.direction && s.direction !== criteria.direction) return false;
    if (criteria.minConfidence !== undefined && s.confidence < criteria.minConfidence) {
      return false;
    }
    const day = (s.bar_timestamp ?? s.created_at).slice(0, 10);
    if (criteria.from && day < criteria.from) return false;
    if (criteria.to && day > criteria.to) return false;
    return true;
  });
}

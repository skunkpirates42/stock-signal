import type { Direction } from "@/lib/types";
import type { SignalCriteria } from "@/lib/filters";

export interface FilterBarProps {
  criteria: SignalCriteria;
  tickers: string[];
  onChange: (criteria: SignalCriteria) => void;
}

const DIRECTIONS: Direction[] = ["LONG", "SHORT", "WAIT"];

export default function FilterBar({ criteria, tickers, onChange }: FilterBarProps) {
  return (
    <div className="filter-bar">
      <label className="filter-field">
        Ticker
        <select
          value={criteria.ticker ?? ""}
          onChange={(e) => onChange({ ...criteria, ticker: e.target.value || undefined })}
        >
          <option value="">All</option>
          {tickers.map((ticker) => (
            <option key={ticker} value={ticker}>
              {ticker}
            </option>
          ))}
        </select>
      </label>

      <label className="filter-field">
        Direction
        <select
          value={criteria.direction ?? ""}
          onChange={(e) =>
            onChange({
              ...criteria,
              direction: (e.target.value || undefined) as Direction | undefined,
            })
          }
        >
          <option value="">Any</option>
          {DIRECTIONS.map((direction) => (
            <option key={direction} value={direction}>
              {direction}
            </option>
          ))}
        </select>
      </label>

      <label className="filter-field">
        Min confidence: {(criteria.minConfidence ?? 0).toFixed(2)}
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={criteria.minConfidence ?? 0}
          onChange={(e) => onChange({ ...criteria, minConfidence: Number(e.target.value) })}
        />
      </label>

      <label className="filter-field">
        From
        <input
          type="date"
          value={criteria.from ?? ""}
          onChange={(e) => onChange({ ...criteria, from: e.target.value || undefined })}
        />
      </label>

      <label className="filter-field">
        To
        <input
          type="date"
          value={criteria.to ?? ""}
          onChange={(e) => onChange({ ...criteria, to: e.target.value || undefined })}
        />
      </label>
    </div>
  );
}

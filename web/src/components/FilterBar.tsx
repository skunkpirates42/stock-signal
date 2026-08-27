import type { Direction } from "@/lib/types";
import type { SignalCriteria } from "@/lib/filters";
import Segmented from "@/components/Segmented";

export interface FilterBarProps {
  criteria: SignalCriteria;
  tickers: string[];
  onChange: (criteria: SignalCriteria) => void;
}

export default function FilterBar({ criteria, tickers, onChange }: FilterBarProps) {
  return (
    <div className="filter-bar">
      <label className="filter-field">
        <span className="micro">Ticker</span>
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

      <div className="filter-field">
        <span className="micro">Direction</span>
        <Segmented
          label="Direction"
          value={criteria.direction}
          onChange={(direction) => onChange({ ...criteria, direction })}
          options={[
            { value: undefined, label: "Any" },
            { value: "LONG" as Direction, label: "Long" },
            { value: "SHORT" as Direction, label: "Short" },
            { value: "WAIT" as Direction, label: "Wait" },
          ]}
        />
      </div>

      <label className="filter-field">
        <span className="micro">Min confidence: {(criteria.minConfidence ?? 0).toFixed(2)}</span>
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
        <span className="micro">From</span>
        <input
          type="date"
          value={criteria.from ?? ""}
          onChange={(e) => onChange({ ...criteria, from: e.target.value || undefined })}
        />
      </label>

      <label className="filter-field">
        <span className="micro">To</span>
        <input
          type="date"
          value={criteria.to ?? ""}
          onChange={(e) => onChange({ ...criteria, to: e.target.value || undefined })}
        />
      </label>
    </div>
  );
}

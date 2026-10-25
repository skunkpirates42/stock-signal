import Link from "next/link";
import type { DateRange } from "@/lib/dateRange";

export interface DateRangeFilterProps {
  range: DateRange;
  scope: "live" | "all";
}

export default function DateRangeFilter({ range, scope }: DateRangeFilterProps) {
  const clearHref = scope === "all" ? "/?source=all" : "/";
  return (
    <form className="filter-bar date-range-filter" method="get" aria-label="Closed-trade date range">
      {scope === "all" && <input type="hidden" name="source" value="all" />}
      <label className="filter-field">
        <span className="micro">Closed from</span>
        <input type="date" name="from" defaultValue={range.from} />
      </label>
      <label className="filter-field">
        <span className="micro">Closed to</span>
        <input type="date" name="to" defaultValue={range.to} />
      </label>
      <div className="date-range-actions">
        <button type="submit" className="button">Apply</button>
        {(range.from || range.to) && <Link href={clearHref}>Clear dates</Link>}
      </div>
    </form>
  );
}

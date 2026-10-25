export interface DateRange {
  from?: string;
  to?: string;
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function validDate(raw: string | undefined): string | undefined {
  if (!raw || !ISO_DATE.test(raw)) return undefined;
  const parsed = new Date(`${raw}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().startsWith(raw) ? raw : undefined;
}

export function closedDateRange(params: { from?: string; to?: string }): DateRange {
  const range: DateRange = {};
  const from = validDate(params.from);
  const to = validDate(params.to);
  if (from) range.from = from;
  if (to) range.to = to;
  return range;
}

export function dateRangeQuery(range: DateRange): URLSearchParams {
  const params = new URLSearchParams();
  if (range.from) params.set("from", range.from);
  if (range.to) params.set("to", range.to);
  return params;
}

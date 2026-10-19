import type { Accounting, Result } from "@/lib/demo";
import { formatCurrency, formatTimestamp, toneForSign } from "@/lib/format";

const VARIANT_ORDER = ["baseline", "strength", "rvol", "both"];

export interface ComparisonEntry {
  id: string;
  pnlLabel: string;
  tone: "positive" | "negative" | "muted";
  synthetic: boolean;
  retrospective: boolean | null;
  coverage: Accounting["coverage"] | null;
}

export interface ComparisonColumn {
  key: string;
  name: string;
  dates: string;
  exactRange: string;
}

export interface ComparisonRow {
  variant: string;
  cells: ComparisonEntry[][];
}

export interface ComparisonTable {
  columns: ComparisonColumn[];
  rows: ComparisonRow[];
  sharedCoverage: Accounting["coverage"] | null;
  sharedRetrospective: boolean | null;
}

const MONTH_DAY = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

export function formatWindowDates(start: string, endExclusive: string): string {
  const startDate = new Date(start);
  const endDate = new Date(endExclusive);
  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
    return `${formatTimestamp(start)} – ${formatTimestamp(endExclusive)}`;
  }
  const startYear = startDate.getUTCFullYear();
  const endYear = endDate.getUTCFullYear();
  const startLabel = startYear === endYear ? MONTH_DAY.format(startDate) : `${MONTH_DAY.format(startDate)}, ${startYear}`;
  return `${startLabel} – ${MONTH_DAY.format(endDate)}, ${endYear}`;
}

function realizedNetPnl(result: Result): number | null {
  const observation = result.metrics.realized_net_pnl?.observation;
  return observation?.availability === "available" ? observation.value : null;
}

function windowKey(result: Result): string {
  return `${result.window.name}|${result.window.start}|${result.window.end_exclusive}`;
}

function sharedValue<T>(values: T[]): T | null {
  return values.length > 0 && values.every((value) => value === values[0]) ? values[0] : null;
}

function compareVariants(left: string, right: string): number {
  const leftRank = VARIANT_ORDER.indexOf(left);
  const rightRank = VARIANT_ORDER.indexOf(right);
  if (leftRank !== -1 && rightRank !== -1) return leftRank - rightRank;
  if (leftRank !== -1) return -1;
  if (rightRank !== -1) return 1;
  return left.localeCompare(right);
}

export function buildComparisonTable(results: Result[]): ComparisonTable {
  const sharedCoverage = sharedValue(results.map((result) => result.accounting.coverage));
  const sharedRetrospective = sharedValue(results.map((result) => result.provenance.retrospective));

  const columnsByKey = new Map<string, ComparisonColumn & { start: string }>();
  for (const result of results) {
    const key = windowKey(result);
    if (columnsByKey.has(key)) continue;
    columnsByKey.set(key, {
      key,
      name: result.window.name,
      dates: formatWindowDates(result.window.start, result.window.end_exclusive),
      exactRange: `${formatTimestamp(result.window.start)} inclusive to ${formatTimestamp(result.window.end_exclusive)} exclusive`,
      start: result.window.start,
    });
  }
  const sortedColumns = [...columnsByKey.values()].sort(
    (left, right) => left.start.localeCompare(right.start) || left.name.localeCompare(right.name),
  );
  const columns = sortedColumns.map(({ key, name, dates, exactRange }) => ({ key, name, dates, exactRange }));
  const columnIndex = new Map(columns.map((column, index) => [column.key, index]));

  const cellsByVariant = new Map<string, ComparisonEntry[][]>();
  for (const result of results) {
    const cells = cellsByVariant.get(result.variant) ?? columns.map(() => []);
    cellsByVariant.set(result.variant, cells);
    const pnl = realizedNetPnl(result);
    cells[columnIndex.get(windowKey(result))!].push({
      id: result.id,
      pnlLabel: pnl === null ? "Unavailable" : formatCurrency(pnl),
      tone: toneForSign(pnl),
      synthetic: result.provenance.synthetic,
      retrospective: sharedRetrospective === null ? result.provenance.retrospective : null,
      coverage: sharedCoverage === null ? result.accounting.coverage : null,
    });
  }
  const rows = [...cellsByVariant.entries()]
    .sort(([left], [right]) => compareVariants(left, right))
    .map(([variant, cells]) => ({ variant, cells }));

  return { columns, rows, sharedCoverage, sharedRetrospective };
}

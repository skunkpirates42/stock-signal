import {
  readArrayOf,
  readBoolean,
  readFields,
  readLiteral,
  readNullable,
  readNumber,
  readOptional,
  readRecordOf,
  readString,
  type Read,
} from "@/lib/parse";

export type Direction = "LONG" | "SHORT" | "WAIT";
export type Vote = "bull" | "bear" | "neutral";
export type Source = "live" | "backtest" | "poc";

export interface Signal {
  id: number;
  ticker: string;
  direction: Direction;
  confidence: number;
  entry: number | null;
  stop: number | null;
  target: number | null;
  rr: number | null;
  bar_timestamp: string | null;
  created_at: string;
  regime: string | null;
  source: Source | null;
  synthesis_source: string | null;
  reasoning: string | null;
  indicators_json: string | null;
}

export interface Trade {
  id: number;
  signal_id: number | null;
  ticker: string;
  direction: Direction;
  entry: number;
  stop: number;
  target: number;
  shares: number;
  exit_price: number | null;
  outcome: "OPEN" | "WIN" | "LOSS" | "BREAKEVEN";
  backend?: string | null;
  account?: string | null;
  remaining_shares?: number | null;
  entry_at?: string | null;
  exit_at?: string | null;
  costs?: number | null;
  pnl: number | null;
  entry_bar: number | null;
  exit_bar: number | null;
  bars_held: number | null;
  created_at: string;
  closed_at: string | null;
  source: Source | null;
}

export interface Breakdown {
  n: number;
  wins: number;
  win_rate: number;
  pnl: number;
}

export interface EquityPoint {
  label: string;
  equity: number;
  pnl: number;
}

export interface Metrics {
  metric_basis?: string;
  gross_pnl?: number;
  costs?: number;
  n_breakeven?: number;
  n_closed: number;
  n_open: number;
  n_wins: number;
  n_losses: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  expectancy: number;
  profit_factor: number | null;
  total_pnl: number;
  max_drawdown: number;
  max_drawdown_pct: number;
  avg_bars_held: number;
  avg_r_multiple: number;
  avg_win_r: number;
  avg_loss_r: number;
  by_ticker: Record<string, Breakdown>;
  by_regime: Record<string, Breakdown>;
  starting_capital: number;
  ending_capital: number;
  equity: EquityPoint[];
}

export interface VoteRow {
  indicator: string;
  label: string;
  vote: Vote;
  detail: string;
}

export interface ExplainResult {
  id: number;
  reasoning: string;
  synthesis_source: string;
  cached: boolean;
}

const readDirection = readLiteral<Direction>("LONG", "SHORT", "WAIT");
const readSource = readNullable(readLiteral<Source>("live", "backtest", "poc"));
const readNullableNumber = readNullable(readNumber);
const readNullableString = readNullable(readString);

export const readSignal: Read<Signal> = (value, path) => {
  const field = readFields(value, path);
  return {
    id: field("id", readNumber),
    ticker: field("ticker", readString),
    direction: field("direction", readDirection),
    confidence: field("confidence", readNumber),
    entry: field("entry", readNullableNumber),
    stop: field("stop", readNullableNumber),
    target: field("target", readNullableNumber),
    rr: field("rr", readNullableNumber),
    bar_timestamp: field("bar_timestamp", readNullableString),
    created_at: field("created_at", readString),
    regime: field("regime", readNullableString),
    source: field("source", readSource),
    synthesis_source: field("synthesis_source", readNullableString),
    reasoning: field("reasoning", readNullableString),
    indicators_json: field("indicators_json", readNullableString),
  };
};

export const readTrade: Read<Trade> = (value, path) => {
  const field = readFields(value, path);
  return {
    id: field("id", readNumber),
    signal_id: field("signal_id", readNullableNumber),
    ticker: field("ticker", readString),
    direction: field("direction", readDirection),
    entry: field("entry", readNumber),
    stop: field("stop", readNumber),
    target: field("target", readNumber),
    shares: field("shares", readNumber),
    exit_price: field("exit_price", readNullableNumber),
    outcome: field("outcome", readLiteral("OPEN", "WIN", "LOSS", "BREAKEVEN")),
    backend: field("backend", readOptional(readNullableString)),
    account: field("account", readOptional(readNullableString)),
    remaining_shares: field("remaining_shares", readOptional(readNullableNumber)),
    entry_at: field("entry_at", readOptional(readNullableString)),
    exit_at: field("exit_at", readOptional(readNullableString)),
    costs: field("costs", readOptional(readNullableNumber)),
    pnl: field("pnl", readNullableNumber),
    entry_bar: field("entry_bar", readNullableNumber),
    exit_bar: field("exit_bar", readNullableNumber),
    bars_held: field("bars_held", readNullableNumber),
    created_at: field("created_at", readString),
    closed_at: field("closed_at", readNullableString),
    source: field("source", readSource),
  };
};

const readBreakdown: Read<Breakdown> = (value, path) => {
  const field = readFields(value, path);
  return {
    n: field("n", readNumber),
    wins: field("wins", readNumber),
    win_rate: field("win_rate", readNumber),
    pnl: field("pnl", readNumber),
  };
};

const readEquityPoint: Read<EquityPoint> = (value, path) => {
  const field = readFields(value, path);
  return {
    label: field("label", readString),
    equity: field("equity", readNumber),
    pnl: field("pnl", readNumber),
  };
};

export const readMetrics: Read<Metrics> = (value, path) => {
  const field = readFields(value, path);
  return {
    metric_basis: field("metric_basis", readOptional(readString)),
    gross_pnl: field("gross_pnl", readOptional(readNumber)),
    costs: field("costs", readOptional(readNumber)),
    n_breakeven: field("n_breakeven", readOptional(readNumber)),
    n_closed: field("n_closed", readNumber),
    n_open: field("n_open", readNumber),
    n_wins: field("n_wins", readNumber),
    n_losses: field("n_losses", readNumber),
    win_rate: field("win_rate", readNumber),
    avg_win: field("avg_win", readNumber),
    avg_loss: field("avg_loss", readNumber),
    expectancy: field("expectancy", readNumber),
    profit_factor: field("profit_factor", readNullableNumber),
    total_pnl: field("total_pnl", readNumber),
    max_drawdown: field("max_drawdown", readNumber),
    max_drawdown_pct: field("max_drawdown_pct", readNumber),
    avg_bars_held: field("avg_bars_held", readNumber),
    avg_r_multiple: field("avg_r_multiple", readNumber),
    avg_win_r: field("avg_win_r", readNumber),
    avg_loss_r: field("avg_loss_r", readNumber),
    by_ticker: field("by_ticker", readRecordOf(readBreakdown)),
    by_regime: field("by_regime", readRecordOf(readBreakdown)),
    starting_capital: field("starting_capital", readNumber),
    ending_capital: field("ending_capital", readNumber),
    equity: field("equity", readArrayOf(readEquityPoint)),
  };
};

export const readExplainResult: Read<ExplainResult> = (value, path) => {
  const field = readFields(value, path);
  return {
    id: field("id", readNumber),
    reasoning: field("reasoning", readString),
    synthesis_source: field("synthesis_source", readString),
    cached: field("cached", readBoolean),
  };
};

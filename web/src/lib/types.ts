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
  remaining_shares?: number;
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

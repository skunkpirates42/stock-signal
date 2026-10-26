export interface MetricDefinition {
  term: string;
  meaning: string;
  formula: string;
}

// Wording mirrors compute_metrics in analytics/metrics.py; change both together.
export const METRIC_DEFINITIONS = {
  expectancy: {
    term: "Expectancy",
    meaning:
      "Average net P&L per closed trade, after recorded costs. Above zero means the average trade made money.",
    formula: "total net P&L ÷ closed trades",
  },
  profitFactor: {
    term: "Profit factor",
    meaning:
      "Dollars the winners made for every dollar the losers lost. Above 1.0 is net profitable. With no losing trades there is nothing to divide by, so it shows —.",
    formula: "total $ won by winning trades ÷ total $ lost by losing trades",
  },
  maxDrawdown: {
    term: "Max drawdown",
    meaning:
      "The largest fall in equity from a high point to a later low, taking closed trades in the order they closed. The percentage is measured from that high point.",
    formula: "largest (running peak equity − equity)",
  },
  avgBarsHeld: {
    term: "Avg bars held",
    meaning: "How long a closed trade stayed open, in five-minute bars. 12 bars is one hour.",
    formula: "total bars held ÷ closed trades",
  },
  rMultiple: {
    term: "R-multiples",
    meaning:
      "A trade's P&L in units of the risk it took at entry. A clean stop is −1R and a clean 2:1 target is +2R; slippage and gaps move results off those marks.",
    formula: "net P&L ÷ (|entry − stop| × shares)",
  },
} satisfies Record<string, MetricDefinition>;

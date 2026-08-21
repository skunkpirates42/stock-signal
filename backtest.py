"""Paper-execution backtest runner.

Replays the synthetic bar series forward for each watchlist ticker, exercising the full
loop: at each bar we either manage the open position (check stop/target) or, if flat in
that ticker, generate a signal and open a paper trade. Closed trades land in the `trades`
table with WIN/LOSS/P&L/bars-held; positions still open at the end stay OPEN.

This stands in for the live intraday loop (which would step bars off the Alpaca websocket
instead of a precomputed series). The engine, executor, and tracker are identical in both.

Run:  python3 backtest.py
"""

from dotenv import load_dotenv

import config
from data.source import active_source_name, get_bars, using_alpaca
from db.logger import close_trade, init_db, log_signal, log_trade_open
from signals.engine import generate_signal
from signals.indicators import compute_indicators
from signals.regime import classify
from trades.executor import PaperBroker
from trades.tracker import check_exit

load_dotenv()


def precompute_regimes(spy_df, qqq_df) -> list:
    """Regime per bar index from the SPY/QQQ series (index-aligned across tickers).

    Returns a list the length of the index series; entries before WARMUP_BARS are None.
    Assumes the watchlist series share a bar index (true for the synthetic generator, and
    approximately true for live REST since all are fetched with the same length/cadence).
    """
    if spy_df is None:
        return []
    n = len(spy_df)
    regimes = [None] * n
    lb = config.BACKTEST_LOOKBACK
    for i in range(config.WARMUP_BARS, n):
        lo = max(0, i - lb + 1)
        spy_ind = compute_indicators(spy_df.iloc[lo : i + 1])
        qqq_ind = compute_indicators(qqq_df.iloc[lo : i + 1]) if qqq_df is not None else None
        regimes[i] = classify(spy_ind, qqq_ind)
    return regimes


def run_ticker(broker: PaperBroker, ticker: str, df, regimes) -> None:
    """Walk one ticker's bars forward, opening/closing paper trades in `broker`."""
    n = len(df)
    for i in range(config.WARMUP_BARS, n):
        bar = df.iloc[i]

        if broker.has_open(ticker):
            position = broker.open_positions[ticker]
            exit_ = check_exit(position, bar)
            if exit_:
                trade = broker.close_position(
                    ticker, exit_["exit_price"], exit_["outcome"], exit_bar=i
                )
                close_trade(position["db_id"], trade)
            continue

        # Flat in this ticker -> look for a fresh entry on this bar.
        # Bounded trailing window (matches the live loop's rolling buffer; keeps this O(n)).
        window = df.iloc[max(0, i - config.BACKTEST_LOOKBACK + 1) : i + 1]
        signal = generate_signal(ticker, compute_indicators(window))
        signal["regime"] = regimes[i] if i < len(regimes) else None
        if signal["direction"] not in ("LONG", "SHORT"):
            continue

        signal_id = log_signal(signal, bar_timestamp=bar["timestamp"])
        position = broker.open_position(signal, entry_bar=i, signal_id=signal_id)
        if position is not None:
            position["db_id"] = log_trade_open(position)


def print_summary(broker: PaperBroker) -> None:
    closed = broker.closed_trades
    wins = [t for t in closed if t["outcome"] == "WIN"]
    losses = [t for t in closed if t["outcome"] == "LOSS"]
    n = len(closed)

    print("=" * 64)
    print("BACKTEST SUMMARY")
    print("=" * 64)
    print(f"{'TICKER':<8}{'DIR':<6}{'ENTRY':>9}{'EXIT':>9}{'OUT':>6}{'PNL':>11}{'BARS':>6}")
    for t in closed:
        print(
            f"{t['ticker']:<8}{t['direction']:<6}{t['entry']:>9.2f}{t['exit_price']:>9.2f}"
            f"{t['outcome']:>6}{t['pnl']:>11.2f}{t['bars_held']:>6}"
        )
    for ticker, p in broker.open_positions.items():
        print(f"{ticker:<8}{p['direction']:<6}{p['entry']:>9.2f}{'-':>9}{'OPEN':>6}{'-':>11}{'-':>6}")

    print("-" * 64)
    total_pnl = sum(t["pnl"] for t in closed)
    win_rate = len(wins) / n if n else 0.0
    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0.0
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0.0
    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss

    print(f"Closed trades:   {n}   (open at end: {len(broker.open_positions)})")
    print(f"Win rate:        {win_rate:.0%}  ({len(wins)}W / {len(losses)}L)")
    print(f"Avg win / loss:  {avg_win:+.2f} / {avg_loss:+.2f}")
    print(f"Expectancy/trade:{expectancy:+.2f}")
    print(f"Realized P&L:    {total_pnl:+.2f}")
    print(f"Ending capital:  {broker.capital:,.2f}  "
          f"(started {config.STARTING_CAPITAL:,.2f}, "
          f"{(broker.capital / config.STARTING_CAPITAL - 1):+.2%})")
    if using_alpaca():
        print("\nNOTE: replay over a few sessions of recent IEX bars — a tiny, "
              "single-regime sample on a partial-volume feed. Validates the live plumbing, "
              "not signal quality. Real validation needs 50+ trades across mixed regimes "
              "accumulated forward (see CLAUDE.md).")
    else:
        print("\nNOTE: synthetic random-walk data — these numbers validate the execution "
              "plumbing only, NOT signal quality. Real validation needs live data and 50+ "
              "closed trades across mixed regimes (see CLAUDE.md).")
    print(f"Logged to {config.DB_PATH}")


def main() -> None:
    print(f"Data source: {active_source_name()}\n")
    init_db()
    broker = PaperBroker()
    # Fetch each ticker once; derive the per-bar regime from SPY/QQQ.
    bars = {t: get_bars(t, n=config.BACKTEST_BARS) for t in config.WATCHLIST}
    regimes = precompute_regimes(bars.get("SPY"), bars.get("QQQ"))
    for ticker in config.WATCHLIST:
        run_ticker(broker, ticker, bars[ticker], regimes)
    print_summary(broker)


if __name__ == "__main__":
    main()

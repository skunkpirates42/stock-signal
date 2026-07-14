"""Performance report entry point.

Loads closed trades from the database and prints the metrics from CLAUDE.md.

Run:  python3 report.py     (after running backtest.py to populate trades)
"""

from analytics.metrics import compute_metrics, format_report, load_closed_trades


def main() -> None:
    trades = load_closed_trades()
    metrics = compute_metrics(trades)
    print(format_report(metrics))
    if metrics["n_closed"]:
        print("\nNOTE: backtest/paper results over a limited sample — not a basis for "
              "conclusions about signal quality. Need 50+ closed trades accumulated forward "
              "across mixed market regimes (see CLAUDE.md).")


if __name__ == "__main__":
    main()

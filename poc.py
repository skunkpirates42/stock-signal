"""PoC entry point.

Runs the full signal pipeline once over the watchlist, on synthetic data when no Alpaca
credentials are configured. Reasoning still hits the network if an LLM provider key
(config.LLM_PROVIDER != "template") is present:

    bars -> indicators -> rule-based signal -> LLM/template reasoning -> print + log

Signals are logged with source="poc" so they're never mistaken for live trading activity.

Run:  python3 poc.py
"""

from dotenv import load_dotenv

import config
from data.source import active_source_name, get_bars
from db.logger import init_db, log_signal
from signals.engine import generate_signal
from signals.indicators import compute_indicators
from signals.llm_synthesis import synthesize
from signals.regime import classify

load_dotenv()  # picks up ANTHROPIC_API_KEY / Alpaca keys if a .env exists


def _print_signal(sig: dict) -> None:
    line = "=" * 64
    print(line)
    print(f"{sig['ticker']:<6}  {sig['direction']:<5}  confidence={sig['confidence']:.0%}")
    print(line)
    t = sig["vote_tally"]
    print(f"  votes: {t['bull']} bull / {t['bear']} bear / {t['neutral']} neutral")
    if sig["direction"] != "WAIT":
        print(
            f"  entry={sig['entry']}  stop={sig['stop']}  "
            f"target={sig['target']}  R:R={sig['rr']}"
        )
    ind = sig["indicators"]
    print(
        f"  rsi={ind['rsi']}  close={ind['close']}  sma20={ind['sma20']}  "
        f"sma50={ind['sma50']}  vwap={ind['vwap']}"
    )
    print(
        f"  macd={ind['macd']}  bb%={ind['bb_pct']}  "
        f"vol_ratio={ind['volume_ratio']:.2f}  atr={ind['atr']}"
    )
    print(f"  [{sig['synthesis_source']}] {sig['reasoning']}")
    print()


def main() -> None:
    print(f"Data source: {active_source_name()}\n")
    init_db()
    results = []

    # Fetch once, compute indicators once, then derive the market regime from SPY/QQQ.
    bars = {t: get_bars(t, n=120) for t in config.WATCHLIST}
    inds = {t: compute_indicators(df) for t, df in bars.items()}
    regime = classify(inds.get("SPY"), inds.get("QQQ"))
    print(f"Market regime: {regime}\n")

    for ticker in config.WATCHLIST:
        signal = generate_signal(ticker, inds[ticker])
        signal["regime"] = regime
        signal = synthesize(signal)
        log_signal(signal, bar_timestamp=bars[ticker]["timestamp"].iloc[-1], source="poc")
        _print_signal(signal)
        results.append(signal)

    # Summary table.
    print("=" * 64)
    print("SUMMARY")
    print("=" * 64)
    print(f"{'TICKER':<8}{'DIRECTION':<11}{'CONF':<8}{'R:R':<6}")
    for s in results:
        rr = f"{s['rr']}" if s["rr"] is not None else "-"
        print(f"{s['ticker']:<8}{s['direction']:<11}{s['confidence']:<8.0%}{rr:<6}")
    n_trades = sum(1 for s in results if s["direction"] != "WAIT")
    print(f"\n{n_trades}/{len(results)} names produced an actionable signal "
          f"(threshold {config.CONFIDENCE_THRESHOLD:.0%}).")
    print(f"Logged to {config.DB_PATH}")


if __name__ == "__main__":
    main()

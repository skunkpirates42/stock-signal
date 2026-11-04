"""Live paper-trading run loop.

Streams 1-minute IEX bars from Alpaca, aggregates them into 5-minute bars, and runs the
signal + paper-execution pipeline on each closed bar during regular trading hours. Writes
signals and trades to the same SQLite DB the backtest/report use.

Run (during/around market hours):  python3 run_live.py     (Ctrl-C to stop)

This is the honest forward-test: unlike the historical backtest, fills happen on bars that
arrive *after* a signal, so realized R:R will start to diverge from the theoretical 2:1.
"""

import logging
import sys

import config
from alerts.desktop import notify_event
from app_logging import configure_logging, log_event
from data.alpaca_stream import BarStream, market_clock
from data.source import using_alpaca
from live.trader import LiveTrader
from live.worker import TradingWorker

logger = logging.getLogger("run_live")


def on_event(kind: str, payload) -> None:
    # flush=True so output appears immediately when piped/redirected (e.g. `| tee live.log`).
    if kind == "signal":
        s = payload
        if s["direction"] == "WAIT":
            return  # keep the console quiet; WAITs are still logged to the DB
        print(
            f"  SIGNAL {s['ticker']:<5} {s['direction']:<5} conf={s['confidence']:.0%} "
            f"entry={s['entry']} stop={s['stop']} target={s['target']} rr={s['rr']}",
            flush=True,
        )
    elif kind == "open":
        p = payload
        print(
            f"  OPEN   {p['ticker']:<5} {p['direction']:<5} {p['shares']} sh @ {p['entry']}",
            flush=True,
        )
    elif kind == "close":
        t = payload
        print(
            f"  CLOSE  {t['ticker']:<5} {t['outcome']:<4} exit={t['exit_price']} "
            f"pnl={t['pnl']:+.2f} bars={t['bars_held']}",
            flush=True,
        )

    # Fire a native desktop notification (best-effort; no-op off macOS or on error).
    notify_event(kind, payload)


def main() -> None:
    configure_logging("live")
    if not using_alpaca():
        sys.exit("No Alpaca credentials in .env — set ALPACA_API_KEY / ALPACA_SECRET_KEY.")

    broker_mode = (
        "ALPACA paper account (real orders)"
        if config.BROKER == "alpaca"
        else "local simulator (no orders leave this machine)"
    )
    print(f"Broker: {broker_mode}.")

    clock = market_clock()
    status = "OPEN" if clock.is_open else "CLOSED"
    print(f"Market is {status} (now {clock.timestamp:%Y-%m-%d %H:%M %Z}).")
    if not clock.is_open:
        print(
            f"Next open: {clock.next_open:%Y-%m-%d %H:%M %Z}. "
            "The loop will connect and idle until bars start flowing."
        )

    trader = LiveTrader(config.WATCHLIST)
    trader.on_event = on_event
    open_n = len(trader.broker.open_positions)
    log_event(
        logger,
        "startup",
        broker=config.BROKER,
        scope=trader.scope,
        account=trader.broker.account,
        db_path=trader.db_path,
        session_policy=config.SESSION_POLICY,
        tickers=",".join(trader.symbols),
        open_positions=open_n,
        blocked=trader.broker.blocked,
    )
    print(
        f"Account capital: {trader.broker.capital:,.2f} "
        f"(reconstructed; {open_n} open position(s) from DB)."
    )

    print(f"Seeding {len(config.WATCHLIST)} watchlist windows from REST history...")
    trader.seed()
    print("Seeded. Subscribing to 1-min IEX bars, aggregating to 5-min. Ctrl-C to stop.\n")

    worker = TradingWorker(trader)
    worker.start()
    stream = BarStream(config.WATCHLIST, worker.on_minute_bar)
    try:
        stream.run()
    except KeyboardInterrupt:
        print("\nStopping. Open positions remain OPEN in the DB; run report.py for metrics.")
    finally:
        worker.stop()
        log_event(logger, "shutdown", scope=trader.scope)


if __name__ == "__main__":
    main()

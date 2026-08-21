# Paper Trading Simulator — Project Context

This file gives Claude Code full context on the project. Read it before doing anything.

---

## What we're building

An AI-powered intraday trading signal platform for personal use, with a paper trading engine that logs every signal and outcome so we can validate reliability before risking real capital. If signal quality proves out over several months, the goal is to productize it as an MVP for other traders.

The reference products we studied: Signa (getsigna.ai) and Aion Analytics. Key insight: Signa uses rule-based indicators + LLM synthesis to produce actionable signals (LONG/SHORT/WAIT). Aion uses trained ML models for probabilistic regime forecasting. We're building closer to Signa's approach first — it's more honest about what it is and more buildable.

---

## Architecture

### Data
- **Alpaca Markets** — primary data source. Free real-time US equity data bundled with a free brokerage account. WebSocket streaming for intraday bars. Also handles paper trade execution.
- **pandas-ta** — technical indicator computation on price series
- **Polygon.io** — fallback/supplementary data if needed (free tier = 15-min delay)
- Do NOT use Yahoo Finance for anything intraday — unreliable and against ToS for commercial use

### Signal engine (Python)
- WebSocket connection to Alpaca streaming API, subscribing to 5-minute bar updates for watchlist
- Maintain rolling window of candles in memory (last 50 bars minimum)
- Recompute indicators on each bar close
- Fire LLM synthesis only when a trigger condition is met — not on every bar

### Signal logic
Nine indicators, each casting a directional vote:

| Indicator | Bullish condition | Bearish condition |
|---|---|---|
| RSI (14) | < 45 (strong: < 30) | > 55 (strong: > 70) |
| Price vs SMA20 | Above | Below |
| SMA20 vs SMA50 | SMA20 > SMA50 | SMA20 < SMA50 |
| Price vs VWAP | Above | Below |
| MACD | Positive | Negative |
| BB position | Near lower band | Near upper band |
| Volume ratio | > 1.2x (confirms direction) | < 0.8x (weakens signal) |

**Threshold:** 62%+ agreement → LONG or SHORT. Below that → WAIT.

**Entry/stop/target:**
- Entry = current price
- Stop = entry ± (ATR × 1.5)
- Target = entry ± (ATR × 3.0)
- R:R should always be ~2:1 minimum before a trade fires

### LLM synthesis
- Model: `claude-sonnet-4-20250514`
- Called only on signal trigger, not every bar
- Prompt receives: ticker, all indicator values, signal direction, confidence score, entry/stop/target
- Returns structured JSON: `{ signal, confidence, entry, stop, target, rr, reasoning }`
- Used for the human-readable reasoning output and journaling — not for the signal decision itself (that's rule-based)

### Trade execution (paper)
- Alpaca paper trading API for simulated fills
- Position sizing: 10% of capital per trade
- Never open a second position in the same ticker while one is open
- Track: entry price, stop, target, shares, entry bar, exit price, outcome (WIN/LOSS/OPEN), P&L, bars held

### Database
- PostgreSQL (or SQLite for local dev)
- Two main tables:

```sql
signals (id, ticker, bar_timestamp, direction, confidence, entry, stop, target, rr, indicators_json, reasoning)
trades (id, signal_id, ticker, direction, entry, stop, target, shares, exit_price, outcome, pnl, entry_bar, exit_bar, bars_held, created_at)
```

- Log every signal regardless of whether a trade fires
- Log every trade outcome as soon as it closes

### Alert delivery
- Telegram bot — primary channel for personal use
- Twilio SMS — optional, add later
- Alert fires on: new signal, trade open, trade close (with P&L)

### Scheduler
- APScheduler or simple cron
- Market hours only: 9:30am–4:00pm ET
- Pre-market job (9:00am): compute EOD indicators on daily bars, generate morning signals
- Intraday: WebSocket streaming, signal checks on each 5-min bar close
- Post-market job (4:30pm): summarize day, log any unclosed trades, send daily P&L summary

---

## Performance metrics to track

These are the metrics that matter for validating signal quality. Log everything from day one.

- **Win rate** — % of closed trades that hit target vs stop
- **Average win / average loss** — in dollars
- **Expectancy** = (win rate × avg win) + (loss rate × avg loss) — must be positive over 50+ trades
- **Max drawdown** — largest peak-to-trough decline in capital
- **R:R realized** — did actual exits match the theoretical R:R?
- **Signal accuracy by ticker** — some tickers may respond better to this logic than others
- **Signal accuracy by market regime** — trending vs choppy markets will show very different results
- **Bars held** — how long trades stay open

Do not draw conclusions from fewer than 50 closed trades. Do not evaluate during a pure bull run only.

---

## Watchlist (starting)

```python
WATCHLIST = ['AAPL', 'NVDA', 'TSLA', 'SPY', 'QQQ', 'MSFT', 'AMZN', 'META']
```

SPY and QQQ serve as market regime context — their signal direction matters for filtering signals on individual names.

---

## What we already built

**The Python backend is built and running** (the original React/JS artifact simulator was
the blueprint; the logic mapped 1:1 and is now the live Python system):

- **Signal engine** — 6 directional votes + volume modifier, pure/tested (`signals/`)
- **Indicators** — hand-rolled in pandas/numpy (pandas-ta unavailable on py3.9); session-anchored VWAP
- **Data** — Alpaca IEX bars (REST history + 1-min websocket), synthetic offline fallback (`data/`)
- **Paper execution** — local `PaperBroker` (default) OR real Alpaca paper orders via `BROKER=alpaca` (`trades/`)
- **Backtest** — replays real multi-month IEX history through the identical engine/executor/tracker
- **Persistence** — SQLite signals + trades logging (`db/`)
- **Analytics + dashboard** — Flask app: equity curve, win/loss, expectancy, drawdown, by-ticker/regime (`dashboard/`)
- **Alerts** — in-dashboard live feed + browser Web Notifications + native macOS banners (`alerts/`).
  Replaced the originally-planned Telegram bot for personal use.
- **Tests** — 58 passing (`tests/`)

### Validation findings so far (real 3-month IEX backtest, ~2,500 trades)

- Win rate ~36% at a ~2:1 reward:risk → **gross expectancy ≈ +$3/trade**, positive across
  both directions and all three regimes (i.e. not just long-bias/beta).
- **But that edge is thinner than realistic transaction costs** — roughly break-even to
  negative after ~$1.50–3.00/trade of friction, and live exit slippage would be worse.
- **Raising the confidence threshold makes it worse, not better** — the 6 votes are all
  price-derived and collinear, so high agreement = late/extended entry. The current 0.62 is
  already the sweet spot; tuning that knob is a dead end.
- Conclusion: the lever is **orthogonal information** (relative strength, real volume, regime
  alignment) used as *quality gates*, not more price-derived votes. See the "State of the
  project" artifact / next-steps notes.

---

## Project structure (target)

```
paper-trader/
├── CLAUDE.md                  # this file
├── .env                       # API keys (never commit)
├── main.py                    # entry point, starts scheduler + websocket
├── config.py                  # watchlist, thresholds, position sizing
├── data/
│   ├── alpaca_stream.py       # websocket bar subscription
│   └── price_store.py         # in-memory rolling window
├── signals/
│   ├── indicators.py          # pandas-ta wrapper, compute all indicators
│   ├── engine.py              # voting logic, threshold, signal generation
│   └── llm_synthesis.py      # Claude API call, structured output
├── trades/
│   ├── executor.py            # Alpaca paper trade execution
│   └── tracker.py             # open/close logic, outcome detection
├── db/
│   ├── models.py              # SQLAlchemy models
│   └── logger.py              # signal + trade logging
├── alerts/
│   └── telegram.py            # Telegram bot alerts
├── dashboard/
│   └── (React frontend — later)
└── tests/
    └── test_signals.py
```

---

## Environment variables needed

```
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ANTHROPIC_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
DATABASE_URL=postgresql://localhost/papertrader
```

---

## Key decisions and why

- **Rule-based signals, not ML** — ML models for price prediction overfit badly without large curated datasets and rigorous walk-forward validation. Rule-based is transparent, debuggable, and honest about what it does. Add ML layer only after collecting real outcome data.
- **LLM for synthesis only, not decisions** — the LLM makes the output readable and useful for journaling. It does not determine the signal. This keeps latency low and costs predictable.
- **Paper trade before live** — validate signal quality over months across different market conditions before touching real capital. The simulator exists specifically for this.
- **Signal delivery only, no auto-execution for MVP** — if this eventually becomes a product, signal delivery (publish research) has minimal regulatory surface. Automated execution on behalf of users crosses into investment adviser territory.
- **Telegram first, no frontend yet** — Telegram is the UI for longer than you think you need it to be. Build the frontend only when going to MVP.

---

## Roadmap

1. **Phase 1 — DONE:** Python backend (Alpaca stream, indicator engine, signal logic, paper
   executor, SQLite logging). Alerts via dashboard/browser/macOS instead of Telegram; dashboard
   built early. Alpaca paper execution wired (opt-in).
2. **Phase 1.5 — signal quality (CURRENT):** The backtest shows a real but *sub-cost* edge, and
   threshold tuning is exhausted. Before accumulating more live data, prove whether **orthogonal
   quality gates** (relative strength, real/RVOL volume, regime alignment) can lift expectancy
   above the cost line. If yes, that's the core improvement; if no, the voting approach needs a
   rethink. Also model transaction costs + realistic exits in the backtest.
3. **Phase 2:** Once a config clears costs in backtest, run it live on Alpaca paper and accumulate
   50+ real trades across mixed regimes to confirm.
4. **Phase 3 (month 3+):** Evaluate honestly. If expectancy is positive across 200+ trades in
   mixed conditions, consider MVP. Options-flow / dealer-gamma data becomes a justified paid
   upgrade only *after* the free orthogonal gates prove the concept.
5. **Phase 4 (MVP):** hardened dashboard, user auth, signal delivery (Telegram/SMS/webhook),
   Stripe billing — signal delivery only, no auto-execution.

---

## What not to build yet

- Options flow / dealer-gamma data (paid ~$50-150/mo) — genuinely orthogonal and the best
  eventual input, but premature: prove the *free* orthogonal gates lift expectancy first, else
  you're stacking an unvalidated paid input on an unvalidated core. Buy gamma/positioning, not
  "unusual activity" flow alerts.
- Broker integration with auto-execution (regulatory complexity, premature)
- ML/trained model layer (need outcome data first)
- Multi-user support (personal use only until signal quality is proven)
- SIP (full-volume) data upgrade — would most help any volume-based signal, but only worth it
  once volume gating shows promise on IEX first.

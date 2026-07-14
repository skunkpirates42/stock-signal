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

A fully working React/JS paper trading simulator (runs in Claude.ai artifact) with:
- Mock intraday price generation
- All 9 indicators computed on each bar
- Signal generation with confidence scoring
- Paper trade execution with position sizing
- Trade log with filtering
- Performance dashboard: equity curve, win/loss distribution, expectancy, drawdown
- Indicator breakdown per ticker

This simulator is the blueprint for the Python backend. The logic maps 1:1.

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

1. **Phase 1 (now):** Python backend — Alpaca stream, indicator engine, signal logic, paper trade executor, PostgreSQL logging, Telegram alerts
2. **Phase 2 (weeks 4–8):** Run live paper trading, accumulate signal/trade data, tune indicator weights and thresholds based on results
3. **Phase 3 (month 3+):** Evaluate signal quality honestly. If expectancy is positive across 200+ trades in mixed market conditions, consider MVP
4. **Phase 4 (MVP):** React dashboard, user auth, signal delivery via Telegram/SMS/webhook, Stripe billing — signal delivery only, no auto-execution

---

## What not to build yet

- Options flow data integration (requires paid data feed ~$50-100/mo, add after core is validated)
- Broker integration with auto-execution (regulatory complexity, premature)
- ML/trained model layer (need outcome data first)
- Frontend dashboard (Telegram is fine for now)
- Multi-user support (personal use only until signal quality is proven)

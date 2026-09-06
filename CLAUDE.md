# Project context

This is a personal, paper-only intraday research system. Use README.md for the current
architecture and commands, docs/implementation-plan.md for the correctness work, and
docs/signal-engine-improvement-plan.md for proposed strategy experiments.

The six-vote engine stays deterministic. LLM synthesis is presentation-only and must
never affect direction or eligibility. Live synthesis is template-only; paid explanation
is on demand. Alpaca execution is hardcoded paper=True.

SQLite journals signals, trades, run manifests and durable orders. Unknown legacy
provenance must remain unknown until supported by explicit evidence. Never replace an
unconfirmed broker fill with a theoretical price. Scope live restoration by source,
backend and account; no replay position may be automatically adopted.

Replay and local live simulation share delayed bar-based fills. Their assumptions differ
from broker-observed market fills. Do not claim validated profitability from the archived
README numbers: the original dataset/configuration are unavailable and the previous
backtest had chronology and ideal-fill defects. New quality gates are opt-in research.

Run backend tests with `.venv/bin/python -m pytest tests/ -q`; frontend tests with
`cd web && pnpm test`. Follow web/AGENTS.md for framework changes. Do not add real-money
execution, multi-user services, paid data, or learned signal models as part of correctness
work. Refer to the separate signal-engine plan for future experiments.

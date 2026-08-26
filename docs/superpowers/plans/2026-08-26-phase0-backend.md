# Phase 0 — Backend Data Integrity and Rationale Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `papertrader.db` honest — every signal and trade tagged with its provenance, every live signal carrying real model-written rationale with a recorded source — so the Next.js dashboard can be built on data that means what it says.

**Architecture:** Three additive SQLite columns applied via the existing `_MIGRATIONS` mechanism, an explicit `source` kwarg threaded through the logging functions, a provider dispatch inside `synthesize()` (no new abstraction layer), and two one-off scripts — one to tag historical rows, one to backfill rationale via the Anthropic Batch API.

**Tech Stack:** Python 3.9.6, stdlib `sqlite3`, pytest, `anthropic` SDK (already installed), `openai` SDK (new, for Groq's OpenAI-compatible endpoint), Flask.

**Spec:** `docs/superpowers/specs/2026-08-26-nextjs-dashboard-design.md`

## Global Constraints

- **Python 3.9.6.** No `match` statements, no `X | Y` type unions, no `dict[str, int]` builtin generics in annotations. Match the existing codebase style.
- **The existing 58 tests must stay green.** Run `python3 -m pytest -q` after every task. Never report a task done without reading that output.
- **Activate the venv first:** `source .venv/bin/activate`. It exists at `.venv/`.
- **Never commit on `main`.** Work happens on the `nextjs-dashboard` branch. Never push.
- **Only one new dependency is authorized:** `openai`, for the Groq path. Nothing else.
- **All schema changes are additive.** No column is dropped, no row is deleted, in any task.
- **Code style:** no docstrings on new private helpers, no section-banner comments, no comments restating what a line does. A single comment is warranted only where the *why* is non-obvious. Tests are exempt.

## Deviation from the spec

Spec §0.2 folds source-tagging into the backfill script behind a `--tag-source` flag. This plan uses **two separate scripts** instead: `scripts/tag_existing_sources.py` (one-off, historical) and `scripts/backfill_reasoning.py` (repeatable). They are different concerns with different lifespans, and combining them would make the backfill script's contract ambiguous.

## File Structure

| File | Responsibility |
|---|---|
| `db/logger.py` (modify) | Schema, migrations, and the `source` / `synthesis_source` persistence |
| `backtest.py` (modify) | Stamps `source="backtest"` on everything it logs |
| `signals/llm_synthesis.py` (rewrite internals) | Provider dispatch + three provider helpers |
| `config.py` (modify) | `LLM_PROVIDER`, `LLM_MODEL`, `GROQ_MODEL`, `GROQ_BASE_URL` |
| `dashboard/app.py` (modify) | `limit` and `source` query params on `/api/signals` |
| `scripts/tag_existing_sources.py` (create) | One-off: tag rows 1–135 as backtest |
| `scripts/backfill_reasoning.py` (create) | Repeatable: fill blank reasoning on live signals |
| `tests/test_logger_provenance.py` (create) | Migration + source persistence |
| `tests/test_llm_synthesis.py` (create) | Provider dispatch + fallback, no network |
| `tests/test_dashboard.py` (modify) | New query params |

---

### Task 1: Schema columns and source persistence

**Files:**
- Modify: `db/logger.py`
- Test: `tests/test_logger_provenance.py`

**Interfaces:**
- Consumes: nothing
- Produces: `log_signal(signal, bar_timestamp=None, db_path=None, source="live") -> int` and `log_trade_open(position, db_path=None, source="live") -> int`. `log_signal` reads `signal.get("synthesis_source")`. Columns `signals.source`, `signals.synthesis_source`, `trades.source` exist on new and pre-existing databases.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_logger_provenance.py`:

```python
"""Provenance columns: source (live|backtest) and synthesis_source (provider:model).

Covers the ALTER-based migration path against a pre-existing database, since the live
papertrader.db predates these columns.
"""

import sqlite3

from db.logger import init_db, log_signal, log_trade_open


def _signal(**over):
    base = {"ticker": "AAA", "direction": "LONG", "confidence": 0.7, "entry": 100.0,
            "stop": 98.0, "target": 104.0, "rr": 2.0, "indicators_json": "{}",
            "reasoning": "because"}
    base.update(over)
    return base


def _position(**over):
    base = {"signal_id": 1, "ticker": "AAA", "direction": "LONG", "entry": 100.0,
            "stop": 98.0, "target": 104.0, "shares": 10, "entry_bar": 1}
    base.update(over)
    return base


def _row(db, table, row_id):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM %s WHERE id = ?" % table, (row_id,)).fetchone()
    conn.close()
    return dict(row)


def _columns(db, table):
    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(%s)" % table)}
    conn.close()
    return cols


def test_migration_adds_columns_to_preexisting_db(tmp_path):
    db = str(tmp_path / "old.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE signals (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "ticker TEXT NOT NULL, direction TEXT NOT NULL, created_at TEXT NOT NULL)")
    conn.execute("CREATE TABLE trades (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "ticker TEXT NOT NULL, direction TEXT NOT NULL, created_at TEXT NOT NULL)")
    conn.commit()
    conn.close()

    init_db(db)

    assert "source" in _columns(db, "signals")
    assert "synthesis_source" in _columns(db, "signals")
    assert "source" in _columns(db, "trades")


def test_init_db_is_idempotent(tmp_path):
    db = str(tmp_path / "d.db")
    init_db(db)
    init_db(db)
    assert "source" in _columns(db, "signals")


def test_log_signal_defaults_source_to_live(tmp_path):
    db = str(tmp_path / "d.db")
    init_db(db)
    sid = log_signal(_signal(), db_path=db)
    assert _row(db, "signals", sid)["source"] == "live"


def test_log_signal_records_explicit_source(tmp_path):
    db = str(tmp_path / "d.db")
    init_db(db)
    sid = log_signal(_signal(), db_path=db, source="backtest")
    assert _row(db, "signals", sid)["source"] == "backtest"


def test_log_signal_persists_synthesis_source(tmp_path):
    db = str(tmp_path / "d.db")
    init_db(db)
    sid = log_signal(_signal(synthesis_source="anthropic:claude-haiku-4-5"), db_path=db)
    assert _row(db, "signals", sid)["synthesis_source"] == "anthropic:claude-haiku-4-5"


def test_log_signal_synthesis_source_is_null_when_absent(tmp_path):
    db = str(tmp_path / "d.db")
    init_db(db)
    sid = log_signal(_signal(), db_path=db)
    assert _row(db, "signals", sid)["synthesis_source"] is None


def test_log_trade_open_defaults_source_to_live(tmp_path):
    db = str(tmp_path / "d.db")
    init_db(db)
    tid = log_trade_open(_position(), db_path=db)
    assert _row(db, "trades", tid)["source"] == "live"


def test_log_trade_open_records_explicit_source(tmp_path):
    db = str(tmp_path / "d.db")
    init_db(db)
    tid = log_trade_open(_position(), db_path=db, source="backtest")
    assert _row(db, "trades", tid)["source"] == "backtest"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
source .venv/bin/activate && python3 -m pytest tests/test_logger_provenance.py -q
```

Expected: failures — `sqlite3.OperationalError: no such column: source`, and `TypeError: log_signal() got an unexpected keyword argument 'source'`.

- [ ] **Step 3: Add the columns to the schemas and migrations**

In `db/logger.py`, add `source TEXT` and `synthesis_source TEXT` to `_SCHEMA`'s column list (after `regime TEXT`), add `source TEXT` to `_TRADES_SCHEMA` (after `closed_at TEXT`), and extend `_MIGRATIONS`:

```python
_MIGRATIONS = [
    "ALTER TABLE signals ADD COLUMN regime TEXT",
    "ALTER TABLE signals ADD COLUMN source TEXT",
    "ALTER TABLE signals ADD COLUMN synthesis_source TEXT",
    "ALTER TABLE trades ADD COLUMN source TEXT",
]
```

The existing `try/except sqlite3.OperationalError: pass` loop in `init_db` already makes re-running safe.

- [ ] **Step 4: Thread `source` through the logging functions**

Change the signature and INSERT in `log_signal`:

```python
def log_signal(signal: dict, bar_timestamp=None, db_path: str = None,
               source: str = "live") -> int:
    """Insert one signal row. Returns the new row id."""
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO signals
                (ticker, bar_timestamp, direction, confidence, entry, stop, target,
                 rr, indicators_json, reasoning, regime, source, synthesis_source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal["ticker"],
                str(bar_timestamp) if bar_timestamp is not None else None,
                signal["direction"],
                signal.get("confidence"),
                signal.get("entry"),
                signal.get("stop"),
                signal.get("target"),
                signal.get("rr"),
                signal.get("indicators_json"),
                signal.get("reasoning"),
                signal.get("regime"),
                source,
                signal.get("synthesis_source"),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return cur.lastrowid
```

And `log_trade_open`:

```python
def log_trade_open(position: dict, db_path: str = None, source: str = "live") -> int:
    """Insert a newly opened trade (outcome OPEN, exit fields null). Returns row id."""
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO trades
                (signal_id, ticker, direction, entry, stop, target, shares,
                 outcome, entry_bar, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?)
            """,
            (
                position.get("signal_id"),
                position["ticker"],
                position["direction"],
                position["entry"],
                position["stop"],
                position["target"],
                position["shares"],
                position["entry_bar"],
                source,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return cur.lastrowid
```

- [ ] **Step 5: Run the new tests**

```bash
source .venv/bin/activate && python3 -m pytest tests/test_logger_provenance.py -q
```

Expected: 8 passed.

- [ ] **Step 6: Run the full suite**

```bash
source .venv/bin/activate && python3 -m pytest -q
```

Expected: 66 passed. If any pre-existing test fails, stop and report — do not modify the failing test to make it pass.

- [ ] **Step 7: Commit**

```bash
git add db/logger.py tests/test_logger_provenance.py
git commit -m "Add source and synthesis_source provenance columns"
```

---

### Task 2: `backtest.py` stamps its own writes

**Files:**
- Modify: `backtest.py:72-75`
- Test: `tests/test_logger_provenance.py` (add one test)

**Interfaces:**
- Consumes: `log_signal(..., source=)` and `log_trade_open(..., source=)` from Task 1
- Produces: nothing new

- [ ] **Step 1: Write the failing test**

Append to `tests/test_logger_provenance.py`:

```python
def test_backtest_module_logs_with_backtest_source():
    """backtest.py must stamp its writes so a mis-pointed DB_PATH is visible, not silent."""
    import inspect

    import backtest

    src = inspect.getsource(backtest.run_ticker)
    assert 'source="backtest"' in src, "backtest.py must pass source='backtest' when logging"
    assert src.count('source="backtest"') >= 2, "both log_signal and log_trade_open need it"
```

Note: this asserts on source text rather than behavior because `run_ticker` requires a full bar DataFrame and a broker to execute. A behavioral test would be better; it is not worth the fixture cost for a two-line change whose failure mode is silent data contamination.

- [ ] **Step 2: Run it to verify it fails**

```bash
source .venv/bin/activate && python3 -m pytest tests/test_logger_provenance.py::test_backtest_module_logs_with_backtest_source -q
```

Expected: FAIL — `AssertionError: backtest.py must pass source='backtest' when logging`.

- [ ] **Step 3: Make the change**

In `backtest.py`, in `run_ticker`, change the two logging calls:

```python
        signal_id = log_signal(signal, bar_timestamp=bar["timestamp"], source="backtest")
        position = broker.open_position(signal, entry_bar=i, signal_id=signal_id)
        if position is not None:
            position["db_id"] = log_trade_open(position, source="backtest")
```

- [ ] **Step 4: Run the test**

```bash
source .venv/bin/activate && python3 -m pytest tests/test_logger_provenance.py -q
```

Expected: 9 passed.

- [ ] **Step 5: Run the full suite**

```bash
source .venv/bin/activate && python3 -m pytest -q
```

Expected: 67 passed.

- [ ] **Step 6: Commit**

```bash
git add backtest.py tests/test_logger_provenance.py
git commit -m "Stamp backtest writes with source=backtest"
```

---

### Task 3: Tag the historical rows in papertrader.db

**Files:**
- Create: `scripts/tag_existing_sources.py`
- Test: manual verification against a copy (steps below)

**Interfaces:**
- Consumes: the `source` columns from Task 1
- Produces: `papertrader.db` with every row tagged `live` or `backtest`

This task mutates the real database. The backup step is not optional.

- [ ] **Step 1: Write the script**

Create `scripts/tag_existing_sources.py`:

```python
"""One-off: tag pre-existing papertrader.db rows with their provenance.

A backtest.py run on 2026-06-10 wrote into papertrader.db before DB_PATH was
env-split. Those rows are ids 1-135 in both tables: 135 signals, 135 trades, zero
WAIT signals, all reasoning blank. Everything from id 136 on is live.

The id cutoff is used here and nowhere else. Run once:

    python3 scripts/tag_existing_sources.py --db papertrader.db --dry-run
    python3 scripts/tag_existing_sources.py --db papertrader.db
"""

import argparse
import sqlite3
import sys

BACKTEST_MAX_ID = 135


def counts(conn):
    out = {}
    for table in ("signals", "trades"):
        rows = conn.execute(
            "SELECT COALESCE(source, 'untagged') AS s, COUNT(*) FROM %s GROUP BY 1" % table
        ).fetchall()
        out[table] = dict(rows)
    return out


def tag(db_path: str, dry_run: bool) -> int:
    conn = sqlite3.connect(db_path)
    print("before:", counts(conn))

    untagged = sum(
        conn.execute("SELECT COUNT(*) FROM %s WHERE source IS NULL" % t).fetchone()[0]
        for t in ("signals", "trades")
    )
    if untagged == 0:
        print("nothing to tag; already done")
        conn.close()
        return 0

    if dry_run:
        for table in ("signals", "trades"):
            n_bt = conn.execute(
                "SELECT COUNT(*) FROM %s WHERE source IS NULL AND id <= ?" % table,
                (BACKTEST_MAX_ID,),
            ).fetchone()[0]
            n_live = conn.execute(
                "SELECT COUNT(*) FROM %s WHERE source IS NULL AND id > ?" % table,
                (BACKTEST_MAX_ID,),
            ).fetchone()[0]
            print("would tag %s: %d backtest, %d live" % (table, n_bt, n_live))
        conn.close()
        return 0

    for table in ("signals", "trades"):
        conn.execute(
            "UPDATE %s SET source = CASE WHEN id <= ? THEN 'backtest' ELSE 'live' END "
            "WHERE source IS NULL" % table,
            (BACKTEST_MAX_ID,),
        )
    conn.commit()
    print("after: ", counts(conn))
    conn.close()
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="papertrader.db")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    return tag(args.db, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Back up the real database**

```bash
cp papertrader.db papertrader.db.pre-tag-backup
ls -la papertrader.db*
```

Expected: `papertrader.db.pre-tag-backup` exists at the same size as `papertrader.db`.

- [ ] **Step 3: Apply the migration to the real DB, then dry-run the tagging**

The columns must exist before tagging. `init_db` is idempotent:

```bash
source .venv/bin/activate
python3 -c "from db.logger import init_db; init_db('papertrader.db'); print('migrated')"
python3 scripts/tag_existing_sources.py --db papertrader.db --dry-run
```

Expected output includes:
```
would tag signals: 135 backtest, 269 live
would tag trades: 135 backtest, 20 live
```

If the numbers differ from 135/269 and 135/20, **stop** — the assumption behind the cutoff is wrong. Report the actual numbers.

- [ ] **Step 4: Run it for real**

```bash
python3 scripts/tag_existing_sources.py --db papertrader.db
```

Expected `after:` line shows `signals: {'backtest': 135, 'live': 269}` and `trades: {'backtest': 135, 'live': 20}`.

- [ ] **Step 5: Verify the metrics split matches the spec**

```bash
source .venv/bin/activate && python3 - <<'PY'
import sqlite3
from analytics.metrics import compute_metrics
conn = sqlite3.connect("papertrader.db"); conn.row_factory = sqlite3.Row
rows = [dict(r) for r in conn.execute("""
  SELECT t.*, s.regime AS regime FROM trades t LEFT JOIN signals s ON t.signal_id=s.id
  WHERE t.source='live' ORDER BY t.closed_at IS NULL, t.closed_at, t.id""")]
m = compute_metrics(rows)
print("live closed:", m["n_closed"], "open:", m["n_open"], "expectancy:", m["expectancy"])
PY
```

Expected: `live closed: 15 open: 5 expectancy: -14.79`. These match the spec's audit table — if they don't, the tagging is wrong.

- [ ] **Step 6: Confirm the suite still passes**

```bash
source .venv/bin/activate && python3 -m pytest -q
```

Expected: 67 passed.

- [ ] **Step 7: Commit the script**

The `.gitignore` excludes `*.db`, so only the script is committed.

```bash
git add scripts/tag_existing_sources.py
git commit -m "Add one-off script tagging pre-existing rows with provenance"
```

---

### Task 4: Provider dispatch in `synthesize()`

**Files:**
- Modify: `signals/llm_synthesis.py`, `config.py`, `requirements.txt`, `.env.example`
- Test: `tests/test_llm_synthesis.py`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces: `synthesize(signal) -> dict` setting `signal["reasoning"]` (str) and `signal["synthesis_source"]` (str: `"template"`, `"anthropic:<model>"`, `"groq:<model>"`, or `"template (fell back from <provider>: <error>)"`). Module-level helpers `_template_reasoning(signal) -> str`, `_anthropic_reasoning(signal) -> tuple`, `_groq_reasoning(signal) -> tuple`, `_prompt_for(signal) -> str`.

- [ ] **Step 1: Add the config**

In `config.py`, replace the `--- LLM ---` block:

```python
# --- LLM -------------------------------------------------------------------
# Synthesis is presentation-only and never affects the trading decision, so any
# provider (or none) is safe. 'template' needs no network and no key.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq").lower()
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-haiku-4-5")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.6-27b")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
```

Groq is the default because its free tier covers this project's volume outright. Anthropic
is a one-line env change (`LLM_PROVIDER=anthropic`), and both degrade to the offline
template on any failure, so a missing key never breaks anything.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_llm_synthesis.py`:

```python
"""Provider dispatch for signal reasoning.

Nothing here touches the network: the anthropic/groq helpers are monkeypatched. The
contract under test is that synthesize() always produces a non-empty reasoning string
and an accurate synthesis_source, whatever the provider does.
"""

import config
from signals import llm_synthesis
from signals.llm_synthesis import synthesize


def _actionable():
    return {
        "ticker": "NVDA", "direction": "LONG", "confidence": 0.7167,
        "entry": 212.5, "stop": 211.6693, "target": 214.1615, "rr": 2.0,
        "votes": {"rsi": "neutral", "price_vs_sma20": "bull", "sma20_vs_sma50": "bull",
                  "price_vs_vwap": "bull", "macd": "bull", "bb": "neutral"},
        "vote_tally": {"bull": 4, "bear": 0, "neutral": 2},
    }


def _wait():
    return {
        "ticker": "AAPL", "direction": "WAIT", "confidence": 0.55,
        "entry": 327.6, "stop": None, "target": None, "rr": None,
        "votes": {"rsi": "neutral", "price_vs_sma20": "bull", "sma20_vs_sma50": "bull",
                  "price_vs_vwap": "bull", "macd": "bear", "bb": "neutral"},
        "vote_tally": {"bull": 3, "bear": 1, "neutral": 2},
    }


def test_template_provider_needs_no_network(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "template")
    out = synthesize(_actionable())
    assert out["synthesis_source"] == "template"
    assert "NVDA" in out["reasoning"]


def test_template_handles_wait_signals(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "template")
    out = synthesize(_wait())
    assert out["synthesis_source"] == "template"
    assert "Standing aside" in out["reasoning"]


def test_anthropic_provider_records_provider_and_model(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(llm_synthesis, "_anthropic_reasoning",
                        lambda s: ("four of six lean bullish", "anthropic:claude-haiku-4-5"))
    out = synthesize(_actionable())
    assert out["reasoning"] == "four of six lean bullish"
    assert out["synthesis_source"] == "anthropic:claude-haiku-4-5"


def test_groq_provider_records_provider_and_model(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(llm_synthesis, "_groq_reasoning",
                        lambda s: ("bullish lean", "groq:qwen/qwen3.6-27b"))
    out = synthesize(_actionable())
    assert out["synthesis_source"] == "groq:qwen/qwen3.6-27b"


def test_provider_failure_falls_back_to_template(monkeypatch):
    def boom(signal):
        raise RuntimeError("api down")

    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(llm_synthesis, "_anthropic_reasoning", boom)
    out = synthesize(_actionable())
    assert "NVDA" in out["reasoning"]
    assert out["synthesis_source"].startswith("template")
    assert "api down" in out["synthesis_source"]


def test_unknown_provider_uses_template(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "nonesuch")
    out = synthesize(_actionable())
    assert out["synthesis_source"] == "template"


def test_prompt_forbids_changing_the_decision():
    prompt = llm_synthesis._prompt_for(_actionable())
    assert "NVDA" in prompt
    assert "LONG" in prompt
    assert "not" in prompt.lower()


def test_wait_prompt_asks_why_it_stood_aside():
    prompt = llm_synthesis._prompt_for(_wait())
    assert "WAIT" in prompt or "stood aside" in prompt.lower()
```

- [ ] **Step 3: Run them to verify they fail**

```bash
source .venv/bin/activate && python3 -m pytest tests/test_llm_synthesis.py -q
```

Expected: failures — `AttributeError: module 'signals.llm_synthesis' has no attribute '_prompt_for'`, and `synthesis_source` mismatches.

- [ ] **Step 4: Rewrite the module internals**

Replace everything in `signals/llm_synthesis.py` below `_template_reasoning` (keep `_template_reasoning` exactly as it is — its output is already correct and eight WAIT/actionable branches depend on it):

```python
def _prompt_for(signal: dict) -> str:
    facts = json.dumps({k: signal.get(k) for k in
                        ("ticker", "direction", "confidence", "entry", "stop", "target",
                         "rr", "votes", "vote_tally")})
    if signal["direction"] == "WAIT":
        task = ("Explain in at most two sentences why this rule-based engine stood aside "
                "(WAIT) on this bar, referencing which indicator votes disagreed.")
    else:
        task = ("Explain in at most two sentences why this rule-based engine fired this "
                "signal, referencing the indicator votes that support it.")
    return (
        "You are summarizing a rule-based intraday trading signal for a personal trading "
        "journal. The decision has already been made by rules; you are not being asked to "
        "evaluate, agree with, or change it. Do not add price predictions or advice. "
        + task
        + " Reply with the explanation text only, no preamble and no JSON.\n\n"
        + "Signal: " + facts
    )


def _anthropic_reasoning(signal: dict):
    from anthropic import Anthropic

    client = Anthropic()
    resp = client.messages.create(
        model=config.LLM_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": _prompt_for(signal)}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not text:
        raise ValueError("empty response")
    return text, "anthropic:%s" % config.LLM_MODEL


def _groq_reasoning(signal: dict):
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ["GROQ_API_KEY"],
        base_url=config.GROQ_BASE_URL,
    )
    resp = client.chat.completions.create(
        model=config.GROQ_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": _prompt_for(signal)}],
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise ValueError("empty response")
    return text, "groq:%s" % config.GROQ_MODEL


def synthesize(signal: dict) -> dict:
    """Attach `reasoning` and `synthesis_source` to the signal.

    Presentation only — never changes the decision. Any provider failure degrades to the
    offline template so the trading loop cannot be blocked by an API outage.
    """
    provider = config.LLM_PROVIDER
    try:
        if provider == "anthropic":
            text, source = _anthropic_reasoning(signal)
        elif provider == "groq":
            text, source = _groq_reasoning(signal)
        else:
            text, source = _template_reasoning(signal), "template"
    except Exception as exc:
        text = _template_reasoning(signal)
        source = "template (fell back from %s: %s)" % (provider, exc)

    signal["reasoning"] = text
    signal["synthesis_source"] = source
    return signal
```

The module already imports `json`, `os`, and `config` at the top — leave those imports in place.

Note: the previous implementation asked for JSON and parsed it. Requesting plain text removes a parse-failure mode for a single-string output.

- [ ] **Step 5: Run the new tests**

```bash
source .venv/bin/activate && python3 -m pytest tests/test_llm_synthesis.py -q
```

Expected: 8 passed.

- [ ] **Step 6: Add the dependency and env documentation**

Append `openai>=1.0` to `requirements.txt`. Add to `.env.example`:

```
# anthropic | groq | template  (template needs no key and no network)
LLM_PROVIDER=groq
GROQ_API_KEY=
GROQ_MODEL=qwen/qwen3.6-27b
LLM_MODEL=claude-haiku-4-5
```

The real `.env` needs `GROQ_API_KEY` filled in. It is already gitignored.

Then install it:

```bash
source .venv/bin/activate && python3 -m pip install "openai>=1.0"
```

- [ ] **Step 7: Run the full suite**

```bash
source .venv/bin/activate && python3 -m pytest -q
```

Expected: 75 passed. `poc.py:45` reads `sig['synthesis_source']` and is the only other consumer of that key; it is a script with no test coverage, so confirm it still parses:

```bash
source .venv/bin/activate && python3 -c "import ast; ast.parse(open('poc.py').read()); print('poc.py parses')"
```

If any test fails, report the failure rather than editing the test.

- [ ] **Step 8: Commit**

```bash
git add signals/llm_synthesis.py config.py requirements.txt .env.example tests/test_llm_synthesis.py
git commit -m "Add anthropic/groq/template provider dispatch for synthesis"
```

---

### Task 5: Backfill script

**Files:**
- Create: `scripts/backfill_reasoning.py`
- Test: manual, via `--dry-run` and `--limit`

**Interfaces:**
- Consumes: `_prompt_for`, `config.LLM_MODEL` from Task 4; `source` column from Task 1
- Produces: `papertrader.db` live signals with non-empty `reasoning` and `synthesis_source`

- [ ] **Step 1: Write the script**

Create `scripts/backfill_reasoning.py`:

```python
"""Backfill reasoning onto live signals that have none.

Idempotent: only touches rows where reasoning is null/empty and source='live'. Safe to
re-run, including to pick up new WAIT signals, which the live loop deliberately does not
synthesize in the bar hot path.

Provider defaults to config.LLM_PROVIDER. The anthropic path uses the Batch API (50%
cheaper, no latency requirement); the groq path issues rate-limited sequential requests,
because Groq's batch endpoint is a paid-plan feature.

    python3 scripts/backfill_reasoning.py --dry-run
    python3 scripts/backfill_reasoning.py --limit 5
    python3 scripts/backfill_reasoning.py
    python3 scripts/backfill_reasoning.py --provider anthropic
"""

import argparse
import json
import sqlite3
import sys
import time

from dotenv import load_dotenv

import config
from signals.llm_synthesis import _prompt_for, _template_reasoning

load_dotenv()

SELECT_BLANK = """
    SELECT id, ticker, direction, confidence, entry, stop, target, rr, indicators_json
      FROM signals
     WHERE source = 'live'
       AND (reasoning IS NULL OR reasoning = '')
     ORDER BY id
"""


def _signal_from_row(row):
    parsed = json.loads(row["indicators_json"] or "{}")
    return {
        "ticker": row["ticker"],
        "direction": row["direction"],
        "confidence": row["confidence"],
        "entry": row["entry"],
        "stop": row["stop"],
        "target": row["target"],
        "rr": row["rr"],
        "votes": parsed.get("votes", {}),
        "vote_tally": parsed.get("tally", {"bull": 0, "bear": 0, "neutral": 0}),
    }


def load_blank(db_path, limit=None):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(SELECT_BLANK).fetchall()
    conn.close()
    rows = list(rows)
    return rows[:limit] if limit else rows


def save(db_path, updates):
    conn = sqlite3.connect(db_path)
    conn.executemany(
        "UPDATE signals SET reasoning = ?, synthesis_source = ? WHERE id = ?", updates
    )
    conn.commit()
    conn.close()


def run_anthropic_batch(rows):
    from anthropic import Anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    client = Anthropic()
    requests = [
        Request(
            custom_id="sig-%d" % r["id"],
            params=MessageCreateParamsNonStreaming(
                model=config.LLM_MODEL,
                max_tokens=300,
                messages=[{"role": "user", "content": _prompt_for(_signal_from_row(r))}],
            ),
        )
        for r in rows
    ]

    batch = client.messages.batches.create(requests=requests)
    print("batch %s submitted with %d requests" % (batch.id, len(requests)))

    while True:
        batch = client.messages.batches.retrieve(batch.id)
        if batch.processing_status == "ended":
            break
        print("  status=%s, waiting..." % batch.processing_status)
        time.sleep(15)

    source = "anthropic:%s" % config.LLM_MODEL
    updates = []
    for result in client.messages.batches.results(batch.id):
        signal_id = int(result.custom_id.split("-")[1])
        if result.result.type != "succeeded":
            print("  id=%d failed: %s" % (signal_id, result.result.type))
            continue
        text = "".join(
            b.text for b in result.result.message.content if b.type == "text"
        ).strip()
        if text:
            updates.append((text, source, signal_id))
    return updates


def _retry_after_seconds(exc, default=20.0):
    """Seconds to wait from a 429, preferring the server's retry-after header."""
    response = getattr(exc, "response", None)
    header = getattr(response, "headers", {}) or {}
    try:
        return float(header.get("retry-after", default))
    except (TypeError, ValueError):
        return default


def run_groq_sequential(rows, db_path, max_retries=5):
    """One request per signal, backing off on 429, checkpointing as it goes.

    Groq's Batch API is a paid-plan feature, so the free tier has no batch path. Free
    limits are per-model and the published example (30 RPM / 8K TPM) makes tokens-per-
    minute the binding constraint at roughly 480 tokens per signal — expect the full
    backfill to take ~15-20 minutes of mostly waiting, so it checkpoints every 25 rows
    rather than risking the whole run to an interrupt.
    """
    from openai import RateLimitError

    from signals.llm_synthesis import _groq_reasoning

    updates = []
    for i, row in enumerate(rows, 1):
        signal = _signal_from_row(row)
        for attempt in range(max_retries):
            try:
                text, source = _groq_reasoning(signal)
                updates.append((text, source, row["id"]))
                break
            except RateLimitError as exc:
                wait = _retry_after_seconds(exc)
                print("  rate limited, sleeping %.1fs (attempt %d/%d)"
                      % (wait, attempt + 1, max_retries))
                time.sleep(wait)
            except Exception as exc:
                print("  id=%d failed: %s" % (row["id"], exc))
                break
        else:
            print("  id=%d gave up after %d rate-limit retries" % (row["id"], max_retries))

        if i % 25 == 0:
            print("  %d/%d done, %d saved" % (i, len(rows), len(updates)))
            save(db_path, updates)
    return updates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="papertrader.db")
    ap.add_argument("--provider", default=config.LLM_PROVIDER, choices=["anthropic", "groq"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = load_blank(args.db, args.limit)
    print("%d live signals with blank reasoning" % len(rows))
    if not rows:
        return 0

    by_direction = {}
    for r in rows:
        by_direction[r["direction"]] = by_direction.get(r["direction"], 0) + 1
    print("by direction:", by_direction)

    if args.dry_run:
        print("\n--- sample prompt (id=%d) ---" % rows[0]["id"])
        print(_prompt_for(_signal_from_row(rows[0])))
        print("\n--- template fallback for comparison ---")
        print(_template_reasoning(_signal_from_row(rows[0])))
        return 0

    print("provider: %s" % args.provider)
    if args.provider == "anthropic":
        updates = run_anthropic_batch(rows)
    else:
        updates = run_groq_sequential(rows, args.db)

    save(args.db, updates)
    print("updated %d of %d rows" % (len(updates), len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Dry-run it**

```bash
source .venv/bin/activate && python3 scripts/backfill_reasoning.py --dry-run
```

Expected: `269 live signals with blank reasoning`, a by-direction breakdown, a readable prompt, and the template fallback. No API call is made. If the count is not 269, stop and report.

- [ ] **Step 3: Back up, then run a 5-row smoke test**

```bash
cp papertrader.db papertrader.db.pre-backfill-backup
source .venv/bin/activate && python3 scripts/backfill_reasoning.py --limit 5
```

Expected on the groq default: `provider: groq`, then `updated 5 of 5 rows`, within seconds
and inside the free tier. On `--provider anthropic`: a batch id, status polling, then the
same result for well under a cent.

This is the first real call to Groq in the project. If the response shape differs from what
`_groq_reasoning` expects, it surfaces here as a template fallback rather than a crash —
check `synthesis_source` in the next step before assuming success.

- [ ] **Step 4: Read the actual output before spending more**

```bash
sqlite3 -line papertrader.db "SELECT id, ticker, direction, synthesis_source, reasoning FROM signals WHERE synthesis_source IS NOT NULL LIMIT 5;"
```

Two checks, both required:

1. **`synthesis_source` must name a real provider** (`groq:qwen/qwen3.6-27b` or
   `anthropic:claude-haiku-4-5`). If it says `template (fell back from groq: ...)`, the
   provider call failed and the error text says why — fix that before continuing. Silently
   backfilling 269 rows of template text relabelled as a backfill is the exact dishonesty
   this whole phase exists to remove.
2. **Read the prose.** It must explain the votes without re-deciding, predicting, or
   advising. If the tone or content is wrong, fix `_prompt_for` in
   `signals/llm_synthesis.py` and re-run the smoke test before proceeding.

- [ ] **Step 5: Run the full backfill**

```bash
source .venv/bin/activate && python3 scripts/backfill_reasoning.py
```

Expected: `264 live signals with blank reasoning`, progress every 25 rows, then
`updated 264 of 264 rows`. On the groq free tier budget **~15-20 minutes**, most of it
sleeping on 429 backoff — that is normal, not a hang. Partial progress is checkpointed
every 25 rows, so an interrupt loses at most 25 rows and re-running resumes.

- [ ] **Step 6: Verify no blanks remain and the suite is green**

```bash
sqlite3 papertrader.db "SELECT source, COUNT(*), SUM(CASE WHEN reasoning IS NULL OR reasoning='' THEN 1 ELSE 0 END) AS blank FROM signals GROUP BY 1;"
source .venv/bin/activate && python3 -m pytest -q
```

Expected: `live|269|0` and `backtest|135|135` (backtest rows are intentionally untouched). 75 passed.

- [ ] **Step 7: Commit**

```bash
git add scripts/backfill_reasoning.py
git commit -m "Add idempotent reasoning backfill script"
```

---

### Task 6: Flask query parameters

**Files:**
- Modify: `dashboard/app.py:29-40` and `dashboard/app.py:52-54`
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: the `source` column from Task 1
- Produces: `GET /api/signals?limit=<int>&source=<live|backtest>` and the same params on `/api/trades`. Both default to current behavior when absent.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_dashboard.py`, and extend `_seed` to add one backtest-sourced signal:

```python
def test_signals_endpoint_respects_limit(tmp_path):
    db = str(tmp_path / "d.db")
    _seed(db)
    for _ in range(5):
        log_signal({"ticker": "CCC", "direction": "WAIT", "confidence": 0.5,
                    "entry": 10, "indicators_json": "{}"}, db_path=db)
    c = create_app(db_path=db).test_client()
    assert len(c.get("/api/signals?limit=3").get_json()) == 3
    assert len(c.get("/api/signals").get_json()) == 6


def test_signals_endpoint_filters_by_source(tmp_path):
    db = str(tmp_path / "d.db")
    _seed(db)
    log_signal({"ticker": "OLD", "direction": "LONG", "confidence": 0.7,
                "entry": 10, "indicators_json": "{}"}, db_path=db, source="backtest")
    c = create_app(db_path=db).test_client()
    live = c.get("/api/signals?source=live").get_json()
    backtest = c.get("/api/signals?source=backtest").get_json()
    assert len(live) == 1 and live[0]["ticker"] == "AAA"
    assert len(backtest) == 1 and backtest[0]["ticker"] == "OLD"


def test_signals_endpoint_rejects_bad_limit(tmp_path):
    db = str(tmp_path / "d.db")
    _seed(db)
    c = create_app(db_path=db).test_client()
    assert c.get("/api/signals?limit=notanumber").status_code == 400
```

- [ ] **Step 2: Run them to verify they fail**

```bash
source .venv/bin/activate && python3 -m pytest tests/test_dashboard.py -q
```

Expected: failures on limit and source filtering; the bad-limit test likely errors with a `ValueError` rather than returning 400.

- [ ] **Step 3: Implement**

In `dashboard/app.py`, replace `_recent` and the two endpoints:

```python
    def _recent(table: str, limit: int = 50, source: str = None):
        conn = sqlite3.connect(_db())
        conn.row_factory = sqlite3.Row
        sql = "SELECT * FROM %s" % table
        params = []
        if source:
            sql += " WHERE source = ?"
            params.append(source)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []  # table not created yet
        finally:
            conn.close()
        return [dict(r) for r in rows]

    def _query_params(default_limit: int):
        raw = request.args.get("limit")
        if raw is None:
            return default_limit, request.args.get("source")
        try:
            return int(raw), request.args.get("source")
        except ValueError:
            abort(400, "limit must be an integer")
```

Flask's `request.args.get(..., type=int)` silently returns the default on a parse failure,
which would make `?limit=notanumber` return 100 rows instead of a 400. Hence the explicit
`int()` and `abort` above.

Then:

```python
    @app.route("/api/trades")
    def api_trades():
        limit, source = _query_params(100)
        return jsonify(_recent("trades", limit, source))

    @app.route("/api/signals")
    def api_signals():
        limit, source = _query_params(100)
        return jsonify(_recent("signals", limit, source))
```

Add `abort` and `request` to the Flask import at the top:

```python
from flask import Flask, abort, jsonify, render_template, request
```

`/api/alerts` calls `_recent("signals", 200)` positionally — the new `source` parameter is
third, so that call keeps working unchanged. Do not modify it.

- [ ] **Step 4: Run the tests**

```bash
source .venv/bin/activate && python3 -m pytest tests/test_dashboard.py -q
```

Expected: all dashboard tests pass, including the three new ones.

- [ ] **Step 5: Run the full suite**

```bash
source .venv/bin/activate && python3 -m pytest -q
```

Expected: 78 passed.

- [ ] **Step 6: Verify against the real database**

```bash
source .venv/bin/activate && python3 run_dashboard.py &
sleep 3
curl -s "http://127.0.0.1:8000/api/signals?source=live&limit=500" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d), 'live signals;', sum(1 for x in d if x['reasoning']), 'with reasoning')"
kill %1
```

Expected: `269 live signals; 269 with reasoning`.

- [ ] **Step 7: Commit**

```bash
git add dashboard/app.py tests/test_dashboard.py
git commit -m "Add limit and source query params to signal and trade endpoints"
```

---

## Phase 0 exit criteria

All must hold before Phase 1 planning begins:

- [ ] `python3 -m pytest -q` reports 78 passed
- [ ] `papertrader.db` has 269 live signals, 0 with blank reasoning
- [ ] Every backfilled row's `synthesis_source` names a real provider — zero rows reading
      `template (fell back from ...)`. Verify with:
      `sqlite3 papertrader.db "SELECT synthesis_source, COUNT(*) FROM signals WHERE source='live' GROUP BY 1;"`
- [ ] `papertrader.db` has 135 backtest signals and 135 backtest trades, all tagged
- [ ] Live-only metrics are 15 closed / 5 open / −$14.79 expectancy
- [ ] `GET /api/signals?source=live&limit=500` returns 269 rows with reasoning and `synthesis_source`
- [ ] Both backup files (`papertrader.db.pre-tag-backup`, `papertrader.db.pre-backfill-backup`) exist and are untracked

## Self-review notes

**Spec coverage:** §0.1 → Task 1. §0.2 → Task 3. §0.3 → Task 2. §0.4 → Task 4. §0.5 → Task 5. §0.6 → Task 6. All six Phase 0 spec sections have a task.

**Known gap, deliberately deferred:** the spec's deployment section calls for `scripts/export_snapshot.py`. It is not in this plan because nothing consumes it until Phase 1 defines the frontend's types. It belongs in the Phase 1 plan.

**Unverifiable from here:** the Groq path (`_groq_reasoning`) has unit tests only against a monkeypatched helper. Its real request/response shape is untested until someone runs it with a `GROQ_API_KEY`, and Groq is now the **default** provider — so Task 5 Step 3 is the first real exercise of it, and Step 4 exists specifically to catch a silent degradation to template text. If the shape is wrong, `--provider anthropic` completes the same backfill for ~$0.11.

**Rate limits are assumed, not published:** Groq documents free-tier limits per model and does not publish the row for `qwen/qwen3.6-27b`. The ~15-20 minute estimate extrapolates from the documented Llama example (30 RPM / 8K TPM). The script honors the server's `retry-after` header rather than relying on that estimate, so a wrong guess costs time, not correctness.

**Model status:** `qwen/qwen3.6-27b` is a preview model that Groq states may be discontinued at short notice. The dispatch degrades to template on failure, and `LLM_PROVIDER=anthropic` is a one-line recovery.

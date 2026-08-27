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
import os
import sqlite3
import sys
import time

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    response = getattr(exc, "response", None)
    header = getattr(response, "headers", {}) or {}
    try:
        return float(header.get("retry-after", default))
    except (TypeError, ValueError):
        return default


def run_groq_sequential(rows, db_path, max_retries=5):
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

        # Free-tier Groq has no batch endpoint, so this run is minutes of mostly rate-limit
        # sleeping; checkpoint every 25 rows so an interrupt loses at most 25, not the run.
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

    # argparse's `choices` only validates a value the user actually typed, not the
    # default — so a --provider-less run with LLM_PROVIDER=template would otherwise
    # silently fall through to the groq branch below and fail on every row.
    if args.provider not in ("anthropic", "groq"):
        ap.error(
            "--provider defaulted to %r (from config.LLM_PROVIDER), which isn't "
            "'anthropic' or 'groq'; pass --provider explicitly" % args.provider
        )

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

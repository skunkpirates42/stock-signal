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

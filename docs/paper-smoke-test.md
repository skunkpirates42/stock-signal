# Opt-in Alpaca paper smoke test

This procedure submits paper orders. Offline tests do not run it automatically.

1. Use a dedicated Alpaca paper account with no unrelated positions/orders, a copied or
   new database, and paper credentials exported locally. Run the offline suites first.
2. Set `BROKER=alpaca` and an explicit `DB_PATH`; start the Flask API and Next.js dashboard
   against that same path. Run `run_live.py` during an exchange session.
3. Verify the displayed broker account scope and a fresh worker heartbeat/data timestamp.
   Observe a candidate, then confirm its journaled client order ID and filled quantity
   against the paper account. Inspect the `orders` table without printing credentials.
4. Restart after an accepted/partially filled order. Confirm lookup adopts its cumulative
   fill without another submission; compare broker direction and remaining quantity with
   the database. A timeout or failed account read must show unresolved/blocked status.
5. Observe a bar-driven exit and verify the trade stays OPEN until all shares are confirmed
   closed. Compare actual average fill, net P&L and trigger reason; a target-triggered
   loss must remain a LOSS.
6. Test `SESSION_POLICY=flatten` in a separate run. Confirm submission before session
   close, including an early-close date when practical. Keep any unresolved exposure
   visible and reconcile it explicitly in the paper account.
7. Stop the runner, record run IDs, account scope, timestamps and discrepancies. Do not
   treat this test as strategy validation. Do not retry an uncertain request with a new
   client ID; investigate the existing journal and broker order first.

The order-ID/reconciliation design follows [Alpaca's order guidance](https://docs.alpaca.markets/us/docs/working-with-orders).
Session queries use [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars).
The pinned calendar supports this repository's Python/pandas versions; review exceptional
exchange closures and dependency updates before running on new periods.

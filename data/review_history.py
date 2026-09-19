"""Read-only Alpaca corporate-action lookup and saved-bar coverage review."""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import config
from data.sessions import utc


def main():
    from alpaca.data.historical.corporate_actions import CorporateActionsClient
    from alpaca.data.requests import CorporateActionsRequest
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset', required=True)
    args = p.parse_args()
    path = Path(args.dataset)
    meta = json.loads(path.with_suffix('.meta.json').read_text())
    dest = path.parent / 'data-review.json'
    if dest.exists():
        raise ValueError('Review already exists; preserve the saved evidence')
    client = CorporateActionsClient(os.environ['ALPACA_API_KEY'], os.environ['ALPACA_SECRET_KEY'], raw_data=True)
    request = client._session.request
    def timed(*args, **kwargs):
        kwargs.setdefault('timeout', (10, 60))
        return request(*args, **kwargs)
    client._session.request = timed
    actions = client.get_corporate_actions(CorporateActionsRequest(
        symbols=meta['symbols'], start=utc(meta['requested_start']).date(),
        end=(utc(meta['requested_end_exclusive']) - pd.Timedelta(days=1)).date(), limit=None))
    (path.parent / 'corporate-actions.json').write_text(json.dumps(actions, indent=2, default=str) + '\n')
    data = json.loads(path.read_text())
    review = {'retrieved_at': datetime.now(timezone.utc).isoformat(), 'corporate_action_counts':
              {k: len(v) for k, v in actions.items()}, 'coverage': {}, 'largest_bar_moves': {}}
    for s, rows in data.items():
        df = pd.DataFrame(rows)
        changes = df.close.pct_change().abs()
        review['largest_bar_moves'][s] = [dict(timestamp=df.timestamp.loc[i], absolute_return=float(changes.loc[i]))
                                         for i in changes.nlargest(3).index]
        c = meta['coverage'][s]
        review['coverage'][s] = {'bars': c['bars'], 'sessions': len(c['sessions']),
                                'missing_buckets': sum(d['missing'] for d in c['sessions'].values()),
                                'empty_sessions': sum(d['observed'] == 0 for d in c['sessions'].values())}
    dest.write_text(json.dumps(review, indent=2) + '\n')
    print(json.dumps(review, indent=2))


if __name__ == '__main__':
    main()

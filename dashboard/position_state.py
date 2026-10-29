"""Read-only, credential-free projection of journaled execution evidence."""
import json
from datetime import datetime, timezone

from db.logger import _connect

STALE_SECONDS = 30  # worker ticks five seconds after its previous tick completes
TERMINAL = {'filled', 'canceled', 'rejected', 'expired', 'done_for_day', 'suspended'}
ACTIVE = {'new', 'accepted', 'partially_filled'}


def fresh(value, at):
    try:
        age = (at - datetime.fromisoformat(value)).total_seconds()
        return 0 <= age <= STALE_SECONDS
    except (TypeError, ValueError):
        return False


def payload(row):
    try:
        value = json.loads(row.get('payload_json') or '{}')
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def provenance(row):
    if row.get('source') in ('backtest', 'poc'):
        return 'Replay'
    if row.get('source') == 'live' and row.get('account'):
        if row.get('backend') == 'alpaca':
            return 'Alpaca paper'
        if row.get('backend') == 'local':
            return 'Local simulation'
    return 'Unknown provenance'


def order_view(row):
    if not row:
        return None
    return {key: row.get(key) for key in ('id', 'state', 'requested_qty', 'filled_qty',
                                         'fill_price', 'updated_at', 'ticker', 'purpose')}


def execution(position, orders, observation, at):
    parent = next((o for o in orders if o['id'] == position.get('entry_order_id')
                   and o['trade_id'] == position['id'] and o['purpose'] == 'entry'), None)
    remaining = position.get('remaining_shares')
    children = [o for o in orders if parent and o['trade_id'] == position['id']
                and payload(o).get('parent_id') == parent['id'] and o['purpose'] == 'exit']
    legs = {}
    confirmed = bool(parent and parent['state'] == 'filled' and remaining and
                     payload(parent).get('execution_policy') == 'bracket_v1')
    for kind in ('stop', 'target'):
        matches = [o for o in children if payload(o).get('exit_reason') == kind]
        child = matches[0] if len(matches) == 1 else None
        quantity = payload(child).get('broker_qty') if child else None
        covered = (isinstance(quantity, (int, float)) and
                   quantity - (child['filled_qty'] or 0) == remaining)
        current = bool(child and fresh(child['updated_at'], at))
        active = bool(child and child['state'] in ACTIVE and covered and current)
        confirmed = confirmed and active
        legs[kind] = {**(order_view(child) or {}), 'state': child['state'] if child else 'missing',
                      'coverage': covered, 'current': current, 'quantity': quantity}
    exits = [o for o in orders if o['trade_id'] == position['id'] and o['purpose'] == 'exit'
             and o['state'] not in TERMINAL and not payload(o).get('parent_id')]
    pending = payload(parent).get('pending_exit') if parent else None
    try:
        pending = json.loads(position.get('state_json') or 'null') or pending
    except (TypeError, ValueError):
        pass
    confirmed = bool(confirmed and observation and observation['status'] == 'ok'
                     and fresh(observation['observed_at'], at) and not pending and not exits)
    return {'entry': order_view(parent), 'legs': legs,
            'protection': 'confirmed' if confirmed else 'unconfirmed',
            'pending_exit': (pending or {}).get('reason') or ('exit pending' if exits else None)}


def position_state(db_path, at=None):
    at = at or datetime.now(timezone.utc)
    with _connect(db_path) as conn:
        conn.execute('BEGIN')  # one consistent journal snapshot across the projection
        positions = [dict(r) for r in conn.execute("SELECT * FROM trades WHERE outcome='OPEN'")]
        orders = [dict(r) for r in conn.execute("SELECT * FROM orders WHERE source='live' AND backend='alpaca' AND account IS NOT NULL")]
        observations = {r['account']: dict(r) for r in conn.execute('SELECT * FROM broker_observations')}
        runtimes = {r['scope']: dict(r) for r in conn.execute('SELECT * FROM runtime_status')}
        closed = [dict(r) for r in conn.execute("SELECT * FROM trades WHERE outcome!='OPEN' ORDER BY id DESC LIMIT 50")]
    accounts = sorted(set(observations) | {o['account'] for o in orders} |
                      {p['account'] for p in positions if provenance(p) == 'Alpaca paper'})
    scopes = []
    for account in accounts:
        obs = observations.get(account)
        scoped = [p for p in positions if provenance(p) == 'Alpaca paper' and p['account'] == account]
        expected = {}
        for p in scoped:
            expected[p['ticker']] = expected.get(p['ticker'], 0) + (p['remaining_shares'] or 0) * (1 if p['direction'] == 'LONG' else -1)
        actual = json.loads(obs['positions_json']) if obs and obs['positions_json'] is not None else None
        current = bool(obs and fresh(obs['observed_at'], at))
        mismatch = actual is not None and actual != expected
        status = ('unavailable' if actual is None else 'stale' if not current else
                  'mismatch' if mismatch else 'unconfirmed' if obs['status'] != 'ok' else
                  'confirmed empty' if not actual else 'observed')
        runtime = runtimes.get(f'live:alpaca:{account}')
        scopes.append({'account': account, 'status': status, 'mismatch': mismatch,
                       'observed_at': obs['observed_at'] if obs else None,
                       'reconciled_at': obs['reconciled_at'] if obs else None,
                       'attempted_at': obs['attempted_at'] if obs else None,
                       'observation_status': obs['status'] if obs else 'unavailable',
                       'heartbeat_at': runtime['updated_at'] if runtime else None,
                       'worker_status': runtime['status'] if runtime else 'unknown',
                       'broker_positions': actual, 'journal_positions': expected})
    for p in positions:
        p['provenance'] = provenance(p)
        p['execution'] = None
        if p['provenance'] == 'Alpaca paper':
            scoped_orders = [o for o in orders if o['account'] == p['account']]
            obs = observations.get(p['account'])
            scope = next(s for s in scopes if s['account'] == p['account'])
            if scope['mismatch'] and obs:
                obs = {**obs, 'status': 'unconfirmed'}
            p['execution'] = execution(p, scoped_orders, obs, at)
        p.pop('state_json', None)
    pending = [{**order_view(o), 'account': o['account'],
                'pending_exit': (payload(o).get('pending_exit') or {}).get('reason'),
                'stop': payload(o).get('stop'), 'target': payload(o).get('target'),
                'execution': execution({'id': None, 'entry_order_id': o['id'], 'remaining_shares': 0},
                    [row for row in orders if row['account'] == o['account']],
                    observations.get(o['account']), at)}
               for o in orders if o['purpose'] == 'entry' and o['trade_id'] is None and o['state'] not in TERMINAL]
    fills = [{**order_view(o), 'account': o['account'], 'reason': payload(o).get('exit_reason')}
             for o in sorted(orders, key=lambda o: o['updated_at'] or '', reverse=True)
             if o['filled_qty'] and o['purpose'] == 'exit'][:50]
    return {'fetched_at': at.isoformat(), 'stale_seconds': STALE_SECONDS,
            'accounts': scopes, 'positions': positions, 'pending_entries': pending,
            'exit_fills': fills, 'closed_trades': closed}

"""Offline integration checks for the additive v2 accounting overlay."""

from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd

from analytics.research_review import marked_metrics
from backtest import distribution_result_posting, replay_historical_corrections, run_portfolio
from db.logger import (cashflow_summary, init_db, load_cashflow_postings,
                       record_cashflow_posting)
from trades.executor import FillPolicy, PaperBroker
from trades.cashflows import DistributionAction, Holding, Settlement, calculate_distribution, calculate_distributions


def _posting(**changes):
    posting = {
        'run_id': 'run-1', 'source': 'backtest', 'backend': 'local', 'account': 'paper',
        'logical_key': 'D1:LONG:A:allocation-1', 'event_kind': 'distribution_accrual',
        'occurred_at': '2026-06-08T04:00:00+00:00', 'action_key': 'D1',
        'revision_key': 'A', 'allocation_key': 'allocation-1', 'receivable_delta': '100.00',
    }
    posting.update(changes)
    return posting


def _bars():
    return {'AAA': pd.DataFrame([
        {'timestamp': '2026-06-10T13:30Z', 'open': 100, 'high': 101, 'low': 99, 'close': 100, 'volume': 1},
        {'timestamp': '2026-06-10T13:35Z', 'open': 100, 'high': 101, 'low': 99, 'close': 100, 'volume': 1},
    ])}


def test_posting_journal_is_scoped_idempotent_and_quarantines_conflicts(tmp_path):
    db = str(tmp_path / 'accounting.db')
    init_db(db)
    first = record_cashflow_posting(_posting(), db)
    assert first['status'] == 'inserted'
    assert record_cashflow_posting(_posting(), db)['status'] == 'duplicate'
    assert record_cashflow_posting(_posting(receivable_delta='120.00'), db)['status'] == 'conflict'
    summary = cashflow_summary('run-1', db, account='paper')
    assert summary['postings'] == 1
    assert summary['conflicts'] == 1
    assert summary['receivable_delta'] == '100.00'


def test_payment_identity_deduplicates_across_revisions_and_overlay_restores(tmp_path):
    db = str(tmp_path / 'payment.db')
    init_db(db)
    assert record_cashflow_posting(_posting(), db)['status'] == 'inserted'
    paid = _posting(event_kind='distribution_settlement', logical_key='payment-a', payment_id='P1',
                    receivable_delta='-100.00', cash_delta='100.00')
    assert record_cashflow_posting(paid, db)['status'] == 'inserted'
    assert record_cashflow_posting({**paid, 'logical_key': 'payment-b', 'revision_key': 'B'}, db)['status'] == 'duplicate'
    summary = cashflow_summary('run-1', db, account='paper')
    restored = PaperBroker(starting_capital=10_000, policy=FillPolicy())
    restored.restore_accounting_state(summary)
    assert restored.accounting_cash == 100
    assert restored.receivables == 0
    assert summary['postings'] == 2


def test_capital_reserves_short_costs_but_not_long_receivables():
    broker = PaperBroker(starting_capital=10_000, position_pct=.1, policy=FillPolicy())
    broker.apply_accounting_posting({'receivable_delta': '100'})
    assert broker.sizing_capital == 10_000
    broker.apply_accounting_posting({'cash_delta': '100', 'receivable_delta': '-100'})
    assert broker.sizing_capital == 10_100

    short = PaperBroker(starting_capital=10_000, position_pct=.1, policy=FillPolicy())
    short.apply_accounting_posting({'payable_delta': '100'})
    assert short.sizing_capital == 9_900
    short.apply_accounting_posting({'cash_delta': '-100', 'payable_delta': '-100'})
    assert short.sizing_capital == 9_900


def test_marked_review_counts_accrual_once_and_settlement_not_twice():
    bars = {'AAA': [
        {'timestamp': '2026-06-10T13:30Z', 'close': 100},
        {'timestamp': '2026-06-10T13:35Z', 'close': 110},
    ]}
    trade = {'ticker': 'AAA', 'direction': 'LONG', 'entry': 100, 'shares': 2,
             'entry_at': '2026-06-10T13:35Z', 'exit_at': None, 'entry_cost': 1, 'pnl': None}
    flows = [
        {'logical_key': 'accrual', 'occurred_at': '2026-06-10T13:35Z', 'receivable_delta': '2'},
        {'logical_key': 'payment', 'occurred_at': '2026-06-10T13:40Z',
         'cash_delta': '2', 'receivable_delta': '-2'},
    ]
    marked = marked_metrics([trade], bars, '2026-06-10', '2026-06-11', 1000, flows)
    assert marked['marked_net_pnl'] == 21
    assert marked['accounting_equity_delta'] == 2
    assert marked['cash_equity_reconciles']


def test_no_applicable_flow_replay_keeps_legacy_metrics_and_correction_artifacts_are_new(tmp_path):
    baseline = run_portfolio(_bars(), str(tmp_path / 'baseline.db'))
    no_flow = run_portfolio(_bars(), str(tmp_path / 'no-flow.db'), accounting_events=())
    assert no_flow['metrics'] == baseline['metrics']

    output = tmp_path / 'corrections'
    results = replay_historical_corrections(
        _bars(),
        {'base': {'accounting_events': [_posting(occurred_at='2026-06-10T13:35Z', run_id='ignored')]},
         'adverse': {'accounting_events': [_posting(occurred_at='2026-06-10T13:35Z', run_id='ignored',
                                                     logical_key='D1:SHORT:A:allocation-1',
                                                     receivable_delta='0', payable_delta='100')] }},
        output,
    )
    assert set(results) == {'base', 'adverse'}
    for name in results:
        assert results[name]['manifest']['historical_correction'] is True
        assert results[name]['manifest']['accounting_mode'] == 'fixed_trade_restatement'
        assert (output / name / 'cashflows.json').exists()
        assert load_cashflow_postings(results[name]['run_id'], str(output / name / 'run.db'))
    assert results['base']['metrics'] == baseline['metrics']
    assert not (Path(tmp_path) / 'baseline' / 'manifest.json').exists()


def test_causal_replay_requires_knowledge_time_and_t02_adapter_is_fixture_only(tmp_path):
    missing = run_portfolio(
        _bars(), str(tmp_path / 'missing-knowledge.db'),
        accounting_events=[_posting(occurred_at='2026-06-10T13:35Z')],
        accounting_coverage=[{'coverage_key': 'borrow-rates', 'status': 'incomplete', 'affected_count': 2}],
    )
    assert missing['accounting']['unavailable_count'] == 3
    assert missing['accounting']['capital_unavailable_count'] == 3
    assert missing['accounting']['available_capital'] == 0
    assert missing['accounting']['postings'] == 1

    at = datetime(2026, 6, 8, 4, tzinfo=timezone.utc)
    result = calculate_distribution(
        (Holding('lot', 'AAA', 'LONG', Decimal('10'), datetime(2026, 6, 5, tzinfo=timezone.utc)),),
        DistributionAction('D1', 'AAA', at, Decimal('1'), currency='USD'),
    ).results[('D1', 'LONG')]
    event = distribution_result_posting(result, at.isoformat(), knowledge_at=at.isoformat())
    assert event['event_kind'] == 'distribution_accrual'
    assert event['receivable_delta'] == Decimal('10.00')


def test_t02_revision_posts_repayment_without_replaying_its_payment(tmp_path):
    at = datetime(2026, 6, 8, 4, tzinfo=timezone.utc)
    lot = Holding('lot', 'AAA', 'LONG', Decimal('100'), datetime(2026, 6, 5, tzinfo=timezone.utc))
    paid = Settlement('P1', 'D1', Decimal('100'), datetime(2026, 6, 15, tzinfo=timezone.utc), currency='USD')
    original = DistributionAction('D1', 'AAA', at, Decimal('1'), currency='USD', revision_id='A')
    corrected = DistributionAction('D1', 'AAA', at, Decimal('.8'), currency='USD', revision_id='B', supersedes_revision='A')
    first = calculate_distribution((lot,), original, (paid,)).results[('D1', 'LONG')]
    revised = calculate_distributions((lot,), (original, corrected), (paid,)).results[('D1', 'LONG')]
    first_event = distribution_result_posting(first, paid.occurred_at.isoformat(), knowledge_at=paid.occurred_at.isoformat())
    revised_event = distribution_result_posting(
        revised, paid.occurred_at.isoformat(), knowledge_at=paid.occurred_at.isoformat(),
        prior={'settled': first.settled, 'receivable': first.receivable,
               'repayment_liability': first.repayment_liability},
    )
    db = str(tmp_path / 'revision.db')
    init_db(db)
    scope = {'run_id': 'revision', 'source': 'backtest', 'backend': 'local', 'account': 'paper'}
    assert record_cashflow_posting({**scope, **first_event}, db)['status'] == 'inserted'
    assert record_cashflow_posting({**scope, **revised_event}, db)['status'] == 'inserted'
    summary = cashflow_summary('revision', db, account='paper')
    assert Decimal(summary['cash_delta']) == Decimal('100.00')
    assert Decimal(summary['repayment_liability_delta']) == Decimal('20.00')


def test_borrow_accrual_intervals_do_not_conflict_and_missing_costs_are_unknown(tmp_path):
    db = str(tmp_path / 'borrow.db')
    init_db(db)
    scope = {'run_id': 'borrow', 'source': 'backtest', 'backend': 'local', 'account': 'paper'}
    for day in ('2026-06-05T00:00:00+00:00', '2026-06-06T00:00:00+00:00'):
        assert record_cashflow_posting({**scope, 'event_kind': 'borrow_accrual', 'occurred_at': day,
                                        'action_key': 'B1', 'allocation_key': 'B1',
                                        'borrow_payable_delta': '5'}, db)['status'] == 'inserted'
    assert cashflow_summary('borrow', db, account='paper')['borrow_payable_delta'] == '10'

    bars = {'AAA': [{'timestamp': '2026-06-10T13:30Z', 'close': 100},
                    {'timestamp': '2026-06-10T13:35Z', 'close': 100}]}
    closed = {'ticker': 'AAA', 'direction': 'LONG', 'entry': 100, 'shares': 1,
              'entry_at': '2026-06-10T13:35Z', 'exit_at': '2026-06-10T13:40Z',
              'exit_price': 100, 'entry_cost': 0, 'pnl': 500}
    marked = marked_metrics([closed], bars, '2026-06-10', '2026-06-11', 1000)
    assert marked['cash_equity_reconciles'] is False
    assert marked['cash_equity_status'] == 'unknown_execution_costs'
    assert marked['cash_equity_max_error'] is None

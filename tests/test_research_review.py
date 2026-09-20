import json

import pytest

import config
from analytics.research_review import (UNCERTAINTY, _decision, marked_metrics,
                                       paired_interval, verify_artifact)
from research import run_comparison


def test_marked_equity_includes_open_costs_closed_net_and_short_exposure():
    bars = {'AAA': [{'timestamp': '2026-06-10T13:30Z', 'close': 100},
                    {'timestamp': '2026-06-10T13:35Z', 'close': 110},
                    {'timestamp': '2026-06-10T13:40Z', 'close': 105}]}
    trade = {'ticker': 'AAA', 'direction': 'LONG', 'entry': 100, 'shares': 2,
             'entry_at': '2026-06-10T13:35Z', 'exit_at': None, 'entry_cost': 1, 'pnl': None}
    m = marked_metrics([trade], bars, '2026-06-10', '2026-06-11', 1000)
    assert m['marked_net_pnl'] == 9
    assert m['max_marked_drawdown'] == 10
    assert m['max_gross_exposure'] == 220
    closed = {**trade, 'exit_at': '2026-06-10T13:40Z', 'exit_price': 110, 'pnl': 18}
    assert marked_metrics([closed], bars, '2026-06-10', '2026-06-11', 1000)['marked_net_pnl'] == 18
    short = {**trade, 'direction': 'SHORT'}
    assert marked_metrics([short], bars, '2026-06-10', '2026-06-11', 1000)['marked_net_pnl'] == -11


def test_paired_bootstrap_is_paired_and_deterministic():
    base = {str(i): float(i) for i in range(20)}
    candidate = {k: v + 2 for k, v in base.items()}
    assert paired_interval(candidate, base)['interval'] == [2, 2]
    assert paired_interval(base, base)['mean_delta'] == 0
    with pytest.raises(ValueError):
        paired_interval({}, base)
    with pytest.raises(ValueError, match='immutable'):
        paired_interval(candidate, base, draws=10)


def test_artifact_checksum_rejection_and_registered_decision_basis(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'SPREAD_BPS', 2)
    monkeypatch.setattr(config, 'SLIPPAGE_BPS', 1)
    output = tmp_path / 'comparison'
    run_comparison('tests/fixtures/bars.json', 'tests/fixtures/windows.json', output,
                   allow_synthetic=True)
    artifact = output / 'development' / 'baseline'
    assert verify_artifact(artifact)['journal']['unknown_or_incomplete'] is False
    bars = json.loads((artifact / 'bars.json').read_text())
    bars['AAA'][0]['close'] += 1
    (artifact / 'bars.json').write_text(json.dumps(bars))
    with pytest.raises(ValueError, match='checksum'):
        verify_artifact(artifact)


def test_unknown_accounting_cannot_be_called_reconciled_or_promotable():
    row = {
        'variant': 'rvol', 'window': 'holdout',
        'marked': {'marked_pnl_by_session': {'a': 1}, 'cash_equity_status': 'reconciled'},
        'expectancy_per_trade': 1, 'accounting_claim_allowed': False,
        'journal_postings_complete': True, 'journal_unknown_or_incomplete': True,
        'paired_session_comparison': {'interval': [1, 2]},
    }
    decision = _decision([row], {'acceptance': {'minimum_sessions': 1}, 'risk_limits': {}}, 1)
    assert decision['status'] == 'inconclusive'
    assert decision['promotable'] is False
    assert 'accounting is not fully reconciled' in decision['reasons']


def test_report_persists_session_and_cost_evidence_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'SPREAD_BPS', 2)
    monkeypatch.setattr(config, 'SLIPPAGE_BPS', 1)
    output = tmp_path / 'comparison'
    summary = run_comparison('tests/fixtures/bars.json', 'tests/fixtures/windows.json',
                             output, allow_synthetic=True)
    row = summary[0]
    inventory = row['diagnostics']['session_inventory']
    assert set(inventory) == {'expected', 'observed', 'incomplete', 'eligible'}
    assert row['diagnostics']['adverse_cost_loss'] is None
    assert row['diagnostics']['stale_data_fraction'] == 0
    protocol = json.loads((output / 'protocol.json').read_text())
    assert protocol['coverage']['development']['SPY']['expected_sessions']

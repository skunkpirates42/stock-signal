import json
from pathlib import Path

import pytest

import config
from research import run_comparison, validate_windows

FIXTURES = Path(__file__).parent / 'fixtures'


def test_windows_require_chronological_development_then_holdout():
    windows = json.loads((FIXTURES / 'windows.json').read_text())
    validate_windows(windows)
    for invalid in ([], windows[:1], list(reversed(windows)),
                    [windows[0], {**windows[1], 'name': '../escape'}],
                    [windows[0], {**windows[1], 'start': windows[0]['start']}],
                    [{**windows[0], 'role': 'holdout'}, {**windows[1], 'role': 'development'}]):
        with pytest.raises(ValueError):
            validate_windows(invalid)


def test_synthetic_and_zero_cost_runs_require_explicit_flags(tmp_path, monkeypatch):
    for key in ('SPREAD_BPS', 'SLIPPAGE_BPS', 'FEE_PER_SHARE'):
        monkeypatch.setattr(config, key, 0)
    args = (FIXTURES / 'bars.json', FIXTURES / 'windows.json', tmp_path / 'out')
    with pytest.raises(ValueError, match='provenance'):
        run_comparison(*args)
    with pytest.raises(ValueError, match='costs'):
        run_comparison(*args, allow_synthetic=True)
    assert not args[2].exists()


def test_four_way_fixture_exports_auditable_diagnostics(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'SPREAD_BPS', 2)
    monkeypatch.setattr(config, 'SLIPPAGE_BPS', 1)
    output = tmp_path / 'comparison'
    args = (FIXTURES / 'bars.json', FIXTURES / 'windows.json', output)
    summary = run_comparison(*args, allow_synthetic=True)
    assert len(summary) == 8
    assert (output / 'comparison.md').exists()
    protocol = json.loads((output / 'protocol.json').read_text())
    assert protocol['costs']['spread_bps'] == 2
    assert protocol['policy']['version'] == 'quality_v2'
    for window in ('development', 'holdout'):
        rows = [r for r in summary if r['window']['name'] == window]
        counts = [sum(r['diagnostics']['candidate_gate_checks'].get(k, 0) for k in ('accepted', 'rejected')) for r in rows]
        assert len(set(counts)) == 1  # portfolio state must not change the candidate population
        for r in rows:
            d = r['diagnostics']
            assert sum(d['closed_net_pnl_by_exit_session'].values()) == pytest.approx(r['metrics']['total_pnl'], abs=.01)
            assert sum(m['n_closed'] for m in d['by_asset_group'].values()) == r['metrics']['n_closed']
    with pytest.raises(ValueError, match='empty'):
        run_comparison(*args, allow_synthetic=True)

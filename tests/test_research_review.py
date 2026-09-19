import pytest
from analytics.research_review import marked_metrics, paired_interval


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

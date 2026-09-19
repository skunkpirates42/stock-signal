import math

import pandas as pd
import pytest

from data.sessions import calendar, session_bounds, utc
from signals.quality import ResearchGate


def frame(rows):
    return pd.DataFrame(rows, columns=['timestamp', 'close', 'volume'])


def evaluate(bars, mode, ts, direction='LONG', symbol='AAA'):
    return ResearchGate(bars, mode)(symbol, {}, utc(ts) + pd.Timedelta(minutes=5), direction)


def test_strength_hand_calculated_and_sides():
    bars = {'AAA': frame([('2026-06-10T13:30Z', 100, 100), ('2026-06-10T14:30Z', 110, 100)]),
            'SPY': frame([('2026-06-10T13:30Z', 100, 100), ('2026-06-10T14:30Z', 105, 100)])}
    accepted, detail = evaluate(bars, 'strength', '2026-06-10T14:30Z')
    assert accepted and detail['strength'] == pytest.approx(math.log(1.1) - math.log(1.05))
    assert not evaluate(bars, 'strength', '2026-06-10T14:30Z', 'SHORT')[0]
    assert evaluate(bars, 'strength', '2026-06-10T14:30Z', symbol='SPY')[1]['checks']['strength']['reason'] == 'not_applicable'
    bars['AAA'] = bars['SPY'].copy()
    assert not evaluate(bars, 'strength', '2026-06-10T14:30Z')[0]


def test_strength_rejects_premarket_stale_and_invalid_endpoints():
    for start, end, price in [('12:30', '13:30', 110), ('13:30', '14:25', 110), ('13:30', '14:30', float('nan'))]:
        rows = [(f'2026-06-10T{start}Z', 100, 100), (f'2026-06-10T{end}Z', price, 100)]
        bars = {'AAA': frame(rows), 'SPY': frame(rows)}
        assert not evaluate(bars, 'strength', f'2026-06-10T{"13:30" if start == "12:30" else "14:30"}Z')[0]


def history(day, count=30, offset=30):
    sessions = [d for d in calendar(int(day[:4])).sessions if str(d.date()) < day][-count:]
    return [(session_bounds(str(d.date()) + 'T17:00Z')[0] + pd.Timedelta(minutes=offset), 100, 100) for d in sessions]


def test_rvol_does_not_reach_back_beyond_twenty_sessions():
    rows = history('2026-06-10')
    # Ten old observations cannot fill holes in the last twenty sessions.
    rows = rows[:10] + rows[-9:] + [('2026-06-10T14:00Z', 100, 200)]
    accepted, detail = evaluate({'AAA': frame(rows)}, 'rvol', '2026-06-10T14:00Z')
    assert not accepted
    assert detail['checks']['rvol']['observations'] == 9


def test_rvol_matches_session_buckets_across_dst_and_ignores_future():
    rows = history('2026-03-10', 20) + [('2026-03-10T14:00Z', 100, 150)]
    before = evaluate({'AAA': frame(rows)}, 'rvol', '2026-03-10T14:00Z')
    assert before[0] and before[1]['rvol'] == 1.5
    rows += [('2026-03-10T14:05Z', 100, 999999), ('2026-03-11T14:00Z', 100, 999999)]
    assert evaluate({'AAA': frame(rows)}, 'rvol', '2026-03-10T14:00Z') == before


def test_rvol_early_close_and_zero_volume():
    rows = history('2026-11-30', 20, offset=300)
    # A fabricated late bucket on Black Friday must not enter the reference.
    rows = [(t, c, 100000 if str(t.date()) == '2026-11-27' else v) for t, c, v in rows]
    rows += [('2026-11-30T19:30Z', 100, 150)]
    result = evaluate({'AAA': frame(rows)}, 'rvol', '2026-11-30T19:30Z')
    assert result[0] and result[1]['checks']['rvol']['observations'] == 19
    zero = [(t, c, 0) for t, c, v in rows]
    assert evaluate({'AAA': frame(zero)}, 'rvol', '2026-11-30T19:30Z')[1]['checks']['rvol']['reason'] == 'zero_reference_volume'


def test_both_requires_both_checks_and_records_each():
    rows = history('2026-06-10', 20) + [('2026-06-10T14:00Z', 100, 150)]
    accepted, detail = evaluate({'AAA': frame(rows)}, 'both', '2026-06-10T14:00Z')
    assert not accepted
    assert detail['checks']['rvol']['accepted']
    assert not detail['checks']['strength']['accepted']

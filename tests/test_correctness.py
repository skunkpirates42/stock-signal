import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import pytest
import config
from backtest import run_portfolio, normalize_bars
from dashboard.app import create_app
from db.logger import init_db, log_trade_open, _connect, load_open_positions
from live.trader import LiveTrader
from data.sessions import in_regular_hours, session_bounds, utc
from trades.executor import PaperBroker, FillPolicy


def bar(ts, close=100, high=None, low=None):
    return dict(timestamp=utc(ts),open=close,close=close,high=high or close+1,low=low or close-1,volume=1000)


def candidate(s,ind):
    return dict(ticker=s,direction='LONG',confidence=.7,entry=ind['close'],stop=98,target=104,rr=2,
                votes={'macd':'bull'},vote_tally={'bull':4,'bear':2,'neutral':0},indicators_json='{}')


def test_configuration_loads_repo_env_before_values_from_other_cwd(tmp_path):
    # Copy config to isolate .env without reading/writing user secrets.
    root=Path(__file__).resolve().parents[1]
    (tmp_path/'config.py').write_text((root/'config.py').read_text())
    (tmp_path/'.env').write_text('BROKER=alpaca\nDASHBOARD_PORT=8123\nDB_PATH=example.db\n')
    env={**os.environ,'PYTHONPATH':str(tmp_path)}
    for k in ('BROKER','DASHBOARD_PORT','DB_PATH'): env.pop(k,None)
    code='import config; print(config.BROKER, config.DASHBOARD_PORT, config.DB_PATH)'
    out=subprocess.check_output([sys.executable,'-c',code],cwd='/tmp',env=env,text=True)
    assert out.strip()=='alpaca 8123 example.db'
    env['BROKER']='local'
    assert subprocess.check_output([sys.executable,'-c',code],cwd='/tmp',env=env,text=True).startswith('local')
    env['BROKER']='invalid'
    assert subprocess.run([sys.executable,'-c',code],cwd='/tmp',env=env,capture_output=True).returncode!=0


def test_new_dashboard_initializes_schema_and_scopes_open_positions(tmp_path):
    db=str(tmp_path/'fresh.db'); client=create_app(db).test_client()
    assert client.get('/api/metrics').get_json()['n_closed']==0
    p=dict(ticker='AAA',direction='LONG',entry=100,stop=98,target=104,shares=10)
    log_trade_open(p,db,source='backtest'); log_trade_open(p,db,source='live')
    assert len(client.get('/api/open').get_json())==1
    assert len(client.get('/api/open?source=all').get_json())==2
    assert client.get('/api/signals?limit=-1').status_code==400


def test_live_restore_isolates_backend_account_and_source(tmp_path):
    db=str(tmp_path/'s.db'); init_db(db)
    p=dict(ticker='AAA',direction='LONG',entry=100,stop=98,target=104,shares=10)
    log_trade_open(p,db,source='backtest')
    log_trade_open({**p,'backend':'alpaca','account':'paper-other'},db)
    log_trade_open({**p,'ticker':'BBB'},db)
    trader=LiveTrader(['AAA','BBB'],db)
    assert set(trader.broker.open_positions)=={'BBB'}


def test_unknown_legacy_position_is_not_adopted(tmp_path):
    db=str(tmp_path/'legacy.db'); init_db(db)
    with _connect(db) as c:
        c.execute("INSERT INTO trades(ticker,outcome) VALUES ('OLD','OPEN')")
    t=LiveTrader(['OLD'],db)
    assert not t.broker.open_positions and t.broker.blocked


def test_sessions_holidays_early_close_and_dst():
    assert not in_regular_hours(utc('2026-07-03T15:00Z'))
    assert session_bounds(utc('2026-11-27T15:00Z'))[1]==utc('2026-11-27T18:00Z')
    assert session_bounds(utc('2026-03-06T16:00Z'))[0]==utc('2026-03-06T14:30Z')
    assert session_bounds(utc('2026-03-09T16:00Z'))[0]==utc('2026-03-09T13:30Z')


def test_final_bucket_clock_flush_and_duplicates(tmp_path):
    t=LiveTrader(['AAA'],str(tmp_path/'b.db'))
    for minute in range(55,60):
        ts=utc(f'2026-06-10T19:{minute}:00Z')
        t.on_minute_bar('AAA',ts,100,101,99,100,10)
        t.on_minute_bar('AAA',ts,100,200,1,100,999)
    t.tick(utc('2026-06-10T20:00:36Z'))
    assert len(t.windows['AAA'])==1
    assert t.windows['AAA'][-1]['volume']==50
    t.tick(utc('2026-06-10T20:01:00Z'))
    assert len(t.windows['AAA'])==1


def test_incomplete_bucket_does_not_fabricate_bar(tmp_path):
    t=LiveTrader(['AAA'],str(tmp_path/'b.db'))
    t.on_minute_bar('AAA',utc('2026-06-10T19:55Z'),100,101,99,100,10)
    t.tick(utc('2026-06-10T20:00:36Z'))
    assert not t.windows['AAA']


def test_replay_order_invariance_historical_fills_and_all_signals(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'WARMUP_BARS',2)
    monkeypatch.setattr('live.trader.compute_indicators',lambda df:{'close':float(df.close.iloc[-1])})
    monkeypatch.setattr('live.trader.generate_signal',candidate)
    timestamps=pd.date_range('2026-06-10T14:00Z',periods=7,freq='5min')
    rows=[bar(ts,c) for ts,c in zip(timestamps,[100,100,101,105,97,100,100])]
    bars={'BBB':pd.DataFrame(rows),'AAA':pd.DataFrame(rows)}
    a=run_portfolio(bars,str(tmp_path/'a.db'))
    b=run_portfolio(dict(reversed(list(bars.items()))),str(tmp_path/'b.db'))
    assert a['metrics']==b['metrics']
    trades=a['trades']
    closed=[t for t in trades if t['outcome']!='OPEN']
    assert len(closed)==2
    assert all(t['entry']==101 and t['exit_price']==97 for t in closed)
    assert all(t['outcome']=='LOSS' and t['exit_reason']=='target' for t in closed)
    assert all(t['entry_at'].startswith('2026-06-10') for t in closed)
    with _connect(str(tmp_path/'a.db')) as c:
        assert c.execute('SELECT count(*) FROM signals').fetchone()[0]==12
        assert {r[0] for r in c.execute('SELECT source FROM signals')}=={'backtest'}


def test_costs_exposure_and_breakeven():
    b=PaperBroker(starting_capital=1000,position_pct=.6,policy=FillPolicy(10,2,.01))
    sig=dict(ticker='AAA',direction='LONG',entry=100,stop=98,target=104)
    a=b.open_position(sig,0)
    second=b.open_position({**sig,'ticker':'BBB'},0)
    assert a['shares']+second['shares']<=9
    t=b.close_position('AAA',100,'target',1)
    assert t['gross_pnl']==0 and t['costs']>0 and t['outcome']=='LOSS'
    b=PaperBroker(policy=FillPolicy())
    b.open_position(sig,0)
    assert b.close_position('AAA',100,'target',1)['outcome']=='BREAKEVEN'


def test_invalid_duplicates_and_future_regime(tmp_path):
    row=bar('2026-06-10T14:00Z')
    with pytest.raises(ValueError): normalize_bars(pd.DataFrame([row,{**row,'close':100.5}]))
    t=LiveTrader(['SPY','QQQ'],str(tmp_path/'c.db'))
    for s in t.symbols:
        t.windows[s].extend([bar('2026-06-10T15:00Z')]*60)
    assert t._regime(utc('2026-06-10T14:00Z')) is None


def test_local_pending_entry_and_exit_survive_restart(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'WARMUP_BARS',1)
    monkeypatch.setattr('live.trader.compute_indicators',lambda df:{'close':float(df.close.iloc[-1])})
    monkeypatch.setattr('live.trader.generate_signal',candidate)
    db=str(tmp_path/'restart.db')
    t=LiveTrader(['AAA'],db)
    t.process_batch({'AAA':bar('2026-06-10T14:00Z')})
    t=LiveTrader(['AAA'],db)
    assert 'AAA' in t.pending
    t.process_batch({'AAA':bar('2026-06-10T14:05Z',101)})
    assert t.broker.open_positions['AAA']['entry']==101
    t.process_batch({'AAA':bar('2026-06-10T14:10Z',105)})
    t=LiveTrader(['AAA'],db)
    t.process_batch({'AAA':bar('2026-06-10T14:15Z',97)})
    assert t.broker.closed_trades[-1]['outcome']=='LOSS'
    assert t.broker.closed_trades[-1]['bars_held']==2


def test_flatten_and_overnight_policies_preserve_no_fill_at_closed_market(tmp_path,monkeypatch):
    for policy in ('flatten','overnight'):
        monkeypatch.setattr(config,'SESSION_POLICY',policy)
        db=str(tmp_path/(policy+'.db'));init_db(db)
        p=dict(ticker='AAA',direction='LONG',entry=100,stop=90,target=120,shares=10,
               entry_at='2026-11-27T17:00:00+00:00',entry_bar=0)
        log_trade_open(p,db)
        t=LiveTrader(['AAA'],db)
        t.process_batch({'AAA':bar('2026-11-27T17:50Z',101)})
        assert t.broker.has_open('AAA')==(policy=='overnight')
        if policy=='flatten':
            assert t.broker.closed_trades[-1]['exit_at'].startswith('2026-11-27T17:55')
        else:
            t.broker.open_positions['AAA']['pending_exit']={'reason':'stop'}
            t.process_batch({'AAA':bar('2026-11-27T17:55Z',89)})
            assert t.broker.has_open('AAA')  # no fill invented at 18:00, when market is closed


def test_future_data_does_not_change_gate_decision():
    from signals.quality import ResearchGate
    ts=pd.date_range('2026-06-10T13:30Z',periods=20,freq='5min')
    bars={'AAA':pd.DataFrame([bar(t,100+i) for i,t in enumerate(ts)]),
          'SPY':pd.DataFrame([bar(t,100) for t in ts])}
    when=ts[12]+pd.Timedelta(minutes=5)
    first=ResearchGate(bars,'strength')('AAA',{},when,'LONG')
    bars['AAA'].loc[bars['AAA'].timestamp>ts[12],'close']=10000
    second=ResearchGate(bars,'strength')('AAA',{},when,'LONG')
    assert first==second and first[0]


def test_rvol_excludes_current_session_and_requires_prior_history():
    from signals.quality import ResearchGate
    dates=pd.bdate_range('2026-06-01',periods=12)
    rows=[bar(str(d.date())+'T14:00Z') for d in dates]
    rows[-1]['volume']=2000
    bars={'AAA':pd.DataFrame(rows)}
    gate=ResearchGate(bars,'rvol')
    assert gate('AAA',{},utc(rows[-1]['timestamp'])+pd.Timedelta(minutes=5),'LONG')[0]
    assert not gate('AAA',{},utc(rows[5]['timestamp'])+pd.Timedelta(minutes=5),'LONG')[0]


def test_market_ingestion_does_not_wait_on_broker_io(tmp_path):
    from live.worker import TradingWorker
    from threading import Event
    entered,release=Event(),Event()
    t=LiveTrader(['AAA'],str(tmp_path/'worker.db'))
    def slow(*args):
        entered.set(); release.wait(2)
    t.on_minute_bar=slow
    w=TradingWorker(t);w.start()
    w.on_minute_bar('AAA',utc('2026-06-10T14:00Z'),100,101,99,100,1)
    assert entered.wait(1)
    w.on_minute_bar('AAA',utc('2026-06-10T14:01Z'),100,101,99,100,1)
    assert w.events.qsize()==1
    release.set();w.stop()


def test_saved_fixture_to_dashboard_api_matches_snapshot(tmp_path):
    root=Path(__file__).parent/'fixtures'
    bars={s:pd.DataFrame(rows) for s,rows in json.loads((root/'bars.json').read_text()).items()}
    db=str(tmp_path/'e2e.db')
    result=run_portfolio(bars,db)
    expected=json.loads((root/'expected-metrics.json').read_text())
    assert result['metrics']==expected
    api=create_app(db).test_client()
    assert api.get('/api/metrics?source=backtest').get_json()==expected
    assert api.get('/api/open').get_json()==[]
    assert len(api.get('/api/open?source=all').get_json())==result['censored_positions']
    assert result['manifest']['dataset_sha256']


def test_invalid_indicator_values_are_wait_and_json_safe():
    from signals.engine import generate_signal
    sig=generate_signal('AAA',{'close':100.,'rsi':float('nan')})
    assert sig['direction']=='WAIT' and sig['skip_reason']=='invalid_indicators'
    assert json.loads(sig['indicators_json'])['values']['rsi'] is None
    json.dumps(sig,allow_nan=False)


def test_monotonic_and_flat_rsi_are_defined():
    from signals.indicators import compute_indicators
    ts=pd.date_range('2026-06-10T13:30Z',periods=60,freq='5min')
    assert compute_indicators(pd.DataFrame([bar(t,100+i) for i,t in enumerate(ts)]))['rsi']==100
    flat=compute_indicators(pd.DataFrame([bar(t,100) for t in ts]))
    assert flat['rsi']==50 and flat['bb_pct']==.5


@pytest.mark.parametrize('module',['poc','backtest','run_live','run_dashboard','report','research','scripts.backfill_reasoning','scripts.tag_existing_sources'])
def test_entrypoint_imports_share_configuration_without_network(tmp_path,module):
    env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]),'DASHBOARD_PORT':'8345',
         'BROKER':'local','LLM_PROVIDER':'template'}
    out=subprocess.check_output([sys.executable,'-c',f'import {module}; import config; print(config.DASHBOARD_PORT)'],
                                cwd=tmp_path,env=env,text=True)
    assert out.strip()=='8345'


def test_minute_aggregation_matches_portfolio_replay(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'WARMUP_BARS',2)
    monkeypatch.setattr('live.trader.compute_indicators',lambda df:{'close':float(df.close.iloc[-1])})
    monkeypatch.setattr('live.trader.generate_signal',candidate)
    times=pd.date_range('2026-06-10T14:00Z',periods=7,freq='5min')
    rows=[bar(ts,c) for ts,c in zip(times,[100,100,101,105,97,100,100])]
    replay=run_portfolio({s:pd.DataFrame(rows) for s in ['BBB','AAA']},str(tmp_path/'replay.db'))
    live=LiveTrader(['AAA','BBB'],str(tmp_path/'live.db'))
    for row in rows:
        for i in range(5):
            for s in ['BBB','AAA']:
                live.on_minute_bar(s,row['timestamp']+pd.Timedelta(minutes=i),row['open'],row['high'],
                                   row['low'],row['close'],row['volume']/5)
    live.tick(times[-1]+pd.Timedelta(minutes=5,seconds=36))
    keys=['ticker','entry','exit_price','pnl','bars_held','outcome']
    a=[{k:t[k] for k in keys} for t in replay['trades'] if t['outcome']!='OPEN']
    b=[{k:t[k] for k in keys} for t in live.broker.closed_trades]
    assert a==b

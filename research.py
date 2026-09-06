"""Fixed gate comparisons on predeclared chronological windows; no threshold search."""
import argparse
import json
from pathlib import Path
import pandas as pd
from backtest import normalize_bars, run_portfolio, export_result
from signals.quality import ResearchGate
from data.sessions import utc


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset', required=True)
    p.add_argument('--windows', required=True, help='JSON list of {name,start,end,role:development|holdout}')
    p.add_argument('--output', required=True)
    args=p.parse_args()
    bars={s:normalize_bars(pd.DataFrame(rows)) for s,rows in json.loads(Path(args.dataset).read_text()).items()}
    meta=Path(args.dataset).with_suffix('.meta.json')
    feed=json.loads(meta.read_text())['feed'] if meta.exists() else 'saved:unknown provenance'
    windows=json.loads(Path(args.windows).read_text())
    previous=None
    summary=[]
    for w in windows:
        start,end=utc(w['start']),utc(w['end'])
        if start>=end or (previous is not None and start<previous) or w['role'] not in ('development','holdout'):
            raise ValueError('Windows must be chronological, nonoverlapping, and labeled development/holdout')
        previous=end
        subset={s:df[df.timestamp<end] for s,df in bars.items()}
        for mode in ('baseline','strength','rvol','both'):
            dest=Path(args.output)/w['name']/mode
            dest.mkdir(parents=True,exist_ok=True)
            result=run_portfolio(subset,str(dest/'run.db'),feed=feed,
                gate=ResearchGate(subset,mode),gate_name=mode,evaluation_start=start,metadata={"window":w,
                "command":["research.py","--dataset",args.dataset,"--windows",args.windows]})
            export_result(result,dest)
            summary.append({'window':w,'variant':mode,'metrics':result['metrics'],
                            'censored_positions':result['censored_positions']})
    (Path(args.output)/'comparison.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    main()

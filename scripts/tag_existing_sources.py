"""Apply an explicit, evidence-backed legacy provenance mapping; never infer by row ID.

Mapping JSON: [{"table":"trades","id":1,"source":"live","backend":"local",
               "account":"local","evidence":"original run log ..."}]
Unknown values remain unknown. Dry-run is available before applying the mapping.
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db.logger import init_db
import config


def tag(db_path, mapping, dry_run=True):
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory=sqlite3.Row
        for item in mapping:
            table=item['table']
            if table not in ('signals','trades') or not item.get('evidence'):
                raise ValueError('Each mapping needs a valid table and evidence')
            if item.get('source') not in ('live','backtest','poc'):
                raise ValueError('Invalid source')
            row=conn.execute(f'SELECT * FROM {table} WHERE id=?',(item['id'],)).fetchone()
            if row is None:
                raise ValueError('Mapped row does not exist')
            changes={k:item[k] for k in ('source','backend','account') if k in item}
            if any(row[k] is not None and row[k]!=v for k,v in changes.items()):
                raise ValueError('Mapping conflicts with existing provenance')
            print(table,item['id'],changes,item['evidence'])
            if not dry_run:
                conn.execute(f"UPDATE {table} SET {','.join(k+'=?' for k in changes)} WHERE id=?",
                             list(changes.values())+[item['id']])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',default=config.DB_PATH)
    p.add_argument('--mapping',required=True)
    p.add_argument('--dry-run',action='store_true')
    args=p.parse_args()
    tag(args.db,json.loads(Path(args.mapping).read_text()),args.dry_run)


if __name__=='__main__':
    main()

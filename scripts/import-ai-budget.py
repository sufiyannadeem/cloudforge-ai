#!/usr/bin/env python3
"""Explicit DBA migration. Never invoked by runtime; source SQLite is read-only.

Freeze ALL old inference workers before importing. Use a stable source-id per
original ledger (not its content hash); repeated imports are idempotent and changed
snapshots are rejected. Finalize only after every historical ledger was imported.
"""
import argparse
import hashlib
import math
import sqlite3
from pathlib import Path
import psycopg


def read_legacy(path):
    file=Path(path).resolve(strict=True)
    with sqlite3.connect(file.as_uri()+'?mode=ro',uri=True) as db:
        rows=db.execute('SELECT id,ts,paise FROM usage ORDER BY id').fetchall()
    for ident,stamp,paise in rows:
        if type(ident) is not int or not math.isfinite(stamp) or type(paise) is not int or paise<0:
            raise ValueError('Invalid legacy reservation')
    # Hash logical rows, including zero-value attempts, to detect altered imports.
    import json
    digest=hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()
    return rows,digest


def import_rows(db,source,rows,digest):
    db.execute('SELECT singleton FROM public.ai_inference_budget WHERE singleton FOR UPDATE')
    existing=db.execute('SELECT sha256 FROM public.ai_inference_imports WHERE source_id=%s',(source,)).fetchone()
    if existing:
        if existing[0]!=digest: raise ValueError('Source changed after import; review required')
        return
    gate=db.execute('SELECT imports_complete FROM public.ai_inference_budget WHERE singleton').fetchone()
    if gate[0]: raise ValueError('Import gate finalized; reviewed additional migration required')
    for ident,stamp,paise in rows:
        nonce='legacy:'+hashlib.sha256(source.encode()).hexdigest()+':'+str(ident)
        db.execute('INSERT INTO public.ai_inference_usage(nonce,body_hash,created_at,reserved_paise) VALUES(%s,%s,to_timestamp(%s),%s)',
                   (nonce,digest,stamp,paise))
    db.execute('UPDATE public.ai_inference_budget SET reserved_paise=reserved_paise+%s WHERE singleton',(sum(r[2] for r in rows),))
    db.execute('INSERT INTO public.ai_inference_imports(source_id,sha256) VALUES(%s,%s)',(source,digest))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-id')
    parser.add_argument('--sqlite')
    parser.add_argument('--finalize',action='store_true')
    args=parser.parse_args()
    if bool(args.source_id)!=bool(args.sqlite) or not(args.sqlite or args.finalize): parser.error('Specify source-id/sqlite or finalize')
    import os
    from psycopg.conninfo import conninfo_to_dict
    dsn=os.environ['DATABASE_URL']
    config=conninfo_to_dict(dsn)
    if config.get('user')!='cf_migrator' or config.get('sslmode')!='verify-full':
        raise ValueError('Dedicated migrator with verified TLS required')
    with psycopg.connect(dsn,connect_timeout=3,options='-c statement_timeout=10000 -c lock_timeout=3000') as db:
        if args.sqlite:
            rows,digest=read_legacy(args.sqlite)
            import_rows(db,args.source_id,rows,digest)
        if args.finalize:
            db.execute('SELECT singleton FROM public.ai_inference_budget WHERE singleton FOR UPDATE')
            db.execute('UPDATE public.ai_inference_budget SET imports_complete=true WHERE singleton')

if __name__=='__main__': main()

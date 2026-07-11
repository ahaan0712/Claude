#!/usr/bin/env python3
import json
from pathlib import Path
from schema import write_json
def main(empty=False):
    if empty: write_json('data/supplemental_discoveries.json', []); return
    old=Path('data/postings.json')
    rows=[]
    if old.exists():
        data=json.load(open(old)); rows=data.get('postings',data if isinstance(data,list) else [])
        for r in rows: r['source_class']='SUPPLEMENTAL_TRACKER'
    write_json('data/supplemental_discoveries.json', rows)
if __name__=='__main__': main()

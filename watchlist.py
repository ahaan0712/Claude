#!/usr/bin/env python3
from datetime import date, timedelta
import json
from pathlib import Path
from schema import write_json
STATUSES={'NOT_DUE','MONITOR_SOON','MONITOR_NOW','OPEN_MATCH_FOUND','OPEN_BUT_INELIGIBLE','OPEN_BUT_OFF_TARGET','CHECKED_NO_MATCH','RETRIEVAL_BLOCKED','RETRIEVAL_FAILED','NEEDS_RESEARCH'}
def status(c,today):
    if c.get('open_match_found'): return 'OPEN_MATCH_FOUND'
    rs=c.get('retrieval_status')
    if rs=='BLOCKED': return 'RETRIEVAL_BLOCKED'
    if rs=='FAILED': return 'RETRIEVAL_FAILED'
    start=c.get('expected_open_start'); mon=c.get('monitoring_start_date') or c.get('next_check_date')
    try: s=date.fromisoformat(start) if start else None
    except Exception: s=None
    try: m=date.fromisoformat(mon) if mon else None
    except Exception: m=None
    if not s: return 'NEEDS_RESEARCH'
    if today>=s: return 'MONITOR_NOW'
    if today>=s-timedelta(days=30): return 'MONITOR_SOON'
    if m and today>=m: return 'MONITOR_SOON'
    return 'NOT_DUE'
def main():
    comps=json.load(open('data/company_watchlist.json')) if Path('data/company_watchlist.json').exists() else []
    today=date.today()
    for c in comps:
        c['monitoring_status']=status(c,today); c.setdefault('current_status','Target retained; no verified live posting yet.'); c.setdefault('last_successful_check',None)
        if not c.get('next_check_date'): c['next_check_date']=(today+timedelta(days=7)).isoformat()
    write_json('data/company_watchlist.json', comps)
if __name__=='__main__': main()

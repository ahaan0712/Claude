#!/usr/bin/env python3
from schema import write_json, now_iso
import json
from pathlib import Path
from datetime import date, timedelta
def main():
    companies=json.load(open('data/company_watchlist.json')) if Path('data/company_watchlist.json').exists() else []
    today=date.today()
    for c in companies:
        c.setdefault('discovery_state','NEEDS_RESEARCH'); c.setdefault('last_checked',None); c.setdefault('next_check_date',(today+timedelta(days=7)).isoformat())
        c.setdefault('current_status','No verified live posting yet; monitor target program')
    write_json('data/company_watchlist.json', companies)
if __name__=='__main__': main()

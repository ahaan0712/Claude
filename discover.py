#!/usr/bin/env python3
from __future__ import annotations
import json, hashlib, time
from pathlib import Path
from urllib.parse import urlparse
from schema import write_json, now_iso
CACHE=Path('data/discovery_cache.json')
def provider_for(url):
    h=urlparse(url or '').netloc.lower(); p=(url or '').lower()
    if 'greenhouse.io' in h or 'greenhouse' in p: return 'Greenhouse'
    if 'lever.co' in h or 'lever' in p: return 'Lever'
    if 'myworkdayjobs' in h or 'workday' in p: return 'Workday'
    if 'oraclecloud' in h or 'oracle' in p: return 'Oracle'
    if url: return 'GenericHTML/JSONLD'
    return 'UNKNOWN'
def main():
    comps=json.load(open('data/company_watchlist.json')) if Path('data/company_watchlist.json').exists() else []
    cache=json.loads(CACHE.read_text()) if CACHE.exists() else {}
    raw=[]
    for c in comps:
        url=c.get('career_page_url') or ''; provider=provider_for(url); c['ats_provider']=provider
        if not url:
            c['retrieval_status']='NEEDS_PROVIDER_SETUP'; c['retrieval_error']='No career-page URL in XLSX'; continue
        key=hashlib.sha1(url.encode()).hexdigest(); cached=cache.get(key)
        # Safe incremental discovery: record provider setup/check metadata only; no invented postings.
        c['last_checked']=now_iso(); c['retrieval_status']='NEEDS_PROVIDER_SETUP'; c['retrieval_error']=f'{provider} adapter requires live-source configuration; no fake posting produced'; cache[key]={'url':url,'provider':provider,'status':c['retrieval_status'],'timestamp':c['last_checked']}
    write_json('data/postings_raw.json', raw); write_json('data/company_watchlist.json', comps); write_json(CACHE, cache)
if __name__=='__main__': main()

#!/usr/bin/env python3
import csv,json,re
from pathlib import Path
from schema import write_json
from companies import normalize_name, names_match
ACTIONS=['APPLY THEN CONTACT','CONTACT BEFORE OPENING','ASK FOR INFORMATIONAL CONVERSATION','RECRUITER CONNECTION AVAILABLE','NO DIRECT NETWORK SIGNAL']
def main():
    companies=json.load(open('data/company_watchlist.json')) if Path('data/company_watchlist.json').exists() else []
    con=Path('Connections.csv'); agg=[]; audit={'raw_files_detected':[p.name for p in Path('.').glob('*.csv') if p.name in ['Connections.csv','Invitations.csv','messages.csv','Email Addresses.csv','PhoneNumbers.csv']],'privacy_action':'Only company-level counts generated; names, emails, profile URLs, messages, and education are not emitted. No alumni inference is performed.'}
    rows=[]
    if con.exists():
        try: rows=list(csv.DictReader(con.open(encoding='utf-8-sig')))
        except Exception: rows=[]
    for c in companies:
        cnt=rel=rec=0; recent=None
        for r in rows:
            comp=next((r.get(k,'') for k in r if k and ('Company' in k or 'company' in k)), '')
            pos=next((r.get(k,'') for k in r if k and ('Position' in k or 'Title' in k or 'title' in k)), '')
            if comp and names_match(c['company'],comp):
                cnt+=1; low=pos.lower(); rel += int(any(x in low for x in ['data','analytics','analyst','science','insight','business intelligence'])); rec += int(any(x in low for x in ['recruit','talent','university']))
        action='NO DIRECT NETWORK SIGNAL'
        if rec: action='RECRUITER CONNECTION AVAILABLE'
        elif rel: action='ASK FOR INFORMATIONAL CONVERSATION'
        elif cnt: action='APPLY THEN CONTACT'
        agg.append({'canonical_company_id':c['canonical_company_id'],'direct_connection_count':cnt,'relevant_analytics_connection_count':rel,'recruiter_or_talent_connection_count':rec,'most_recent_connection_date':recent,'followed_company':False,'networking_opportunity_level':'HIGH' if rec or rel else ('MEDIUM' if cnt else 'NONE'),'recommended_networking_action':action})
    write_json('data/network_aggregates.json', agg); write_json('data/network_audit.json', audit)
if __name__=='__main__': main()

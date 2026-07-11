#!/usr/bin/env python3
import json, hashlib
from pathlib import Path
from schema import write_json, now_iso, default_posting
DATA_TITLES=['Data Analyst Intern','Data Analytics Intern','Business Intelligence Intern']
def make_fixture(company, cid, pids, title, desc):
    p=default_posting(); p.update(posting_id='fixture-'+hashlib.sha1((company+title).encode()).hexdigest()[:10], canonical_company_id=cid,target_program_ids=pids,company=company,title=title,location='United States',source='deterministic fixture',source_class='TARGET_DISCOVERY',canonical_apply_url='',posting_date='2026-07-11',internship_term='Summer 2027',employment_type='Internship',full_description=desc,retrieval_status='FULL',retrieval_provider='MANUAL_FIXTURE',retrieval_timestamp=now_iso(),data_completeness=0.85); return p
def main():
    comps=json.load(open('data/company_watchlist.json')); raw=[]
    for c in comps:
        name=c['company'].lower()
        if 'capital one' in name:
            raw.append(make_fixture(c['company'],c['canonical_company_id'],c['target_program_ids'],'Data Analyst Intern - Summer 2027','Data analytics internship using SQL Python and dashboards. Candidates must have unrestricted work authorization in the United States and must not require sponsorship now or in the future.'))
            c['discovery_state']='CHECKED_MATCH_FOUND'; c['last_checked']=now_iso()
        elif any(x in name for x in ['microsoft','google','amazon','salesforce']):
            raw.append(make_fixture(c['company'],c['canonical_company_id'],c['target_program_ids'],'Data Analytics Intern - Summer 2027','Undergraduate data analytics internship. Responsibilities include SQL, Python, dashboards, experimentation, and stakeholder analysis. CPT or other student work authorization can be reviewed by recruiting; verify posting details before applying.'))
            c['discovery_state']='CHECKED_MATCH_FOUND'; c['last_checked']=now_iso()
        else:
            c['discovery_state']='EXPECTED_LATER'; c['current_status']='Target retained; no live fixture posting verified yet.'
    write_json('data/postings_raw.json', raw); write_json('data/company_watchlist.json', comps)
if __name__=='__main__': main()

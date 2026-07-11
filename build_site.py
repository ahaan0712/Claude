#!/usr/bin/env python3
import shutil, json, re
from pathlib import Path
PUBLIC=['target_programs.json','company_watchlist.json','live_matches.json','review_queue.json','excluded_postings.json','closed_postings.json','supplemental_discoveries.json','coverage_report.json','network_aggregates.json','lane_calibration.json','model_evaluation.json','feature_audit.json','company_reconciliation_report.json','repository_reconciliation_report.json']
BLOCK_EXT={'.py','.xlsx','.docx','.zip','.csv'}
DENY=['Connections.csv','Invitations','messages','Email Addresses','PhoneNumbers','.git','Profile.csv','Resume','Target List']
def main():
    site=Path('site'); shutil.rmtree(site, ignore_errors=True); (site/'data').mkdir(parents=True)
    shutil.copyfile('index.html', site/'index.html')
    for f in PUBLIC:
        p=Path('data')/f
        if p.exists(): shutil.copyfile(p, site/'data'/f)
    bad=[]
    for p in site.rglob('*'):
        if any(d in str(p) for d in DENY) or p.suffix in BLOCK_EXT: bad.append(str(p))
    if bad: raise SystemExit('privacy check failed: '+str(bad))
if __name__=='__main__': main()

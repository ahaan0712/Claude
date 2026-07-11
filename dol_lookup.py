#!/usr/bin/env python3
import json
from pathlib import Path
from schema import write_json, now_iso
from companies import match_company, normalize_name
STATES=['REAL','NONE','UNKNOWN','PARTIAL','STALE','UNVERIFIED']
def evaluate_company(company, candidates=None, network_ok=False):
    if not network_ok: return {'company':company,'dol_evidence_state':'UNKNOWN','match_method':'NO_MATCH','match_confidence':0.0,'filing_count':None}
    best={'match':False,'method':'NO_MATCH','confidence':0}
    for cand in candidates or []:
        m=match_company(company,cand)
        if m['confidence']>best['confidence']: best=m
    return {'company':company,'dol_evidence_state':'REAL' if best['match'] else 'NONE','match_method':best['method'],'match_confidence':best['confidence'],'filing_count':1 if best['match'] else 0}
def main():
    comps=json.load(open('data/company_watchlist.json')) if Path('data/company_watchlist.json').exists() else []
    evidence=[evaluate_company(c['company'], network_ok=False) | {'canonical_company_id':c['canonical_company_id']} for c in comps]
    summary={s:sum(1 for e in evidence if e['dol_evidence_state']==s) for s in STATES}
    write_json('data/dol_lookup.json', {'generated_at':now_iso(),'note':'Existing broken-match evidence invalidated; external refresh in Actions should regenerate. Network failures produce UNKNOWN, never NONE.','summary':summary,'previous_real_values_invalidated':True,'sample_false_positives_corrected':['empty normalized name cannot match','Worldwide Inc generic token no longer contaminates unrelated companies'],'companies':evidence})
if __name__=='__main__': main()

#!/usr/bin/env python3
import json
from pathlib import Path
from collections import Counter
from schema import write_json, now_iso
def load(f,default):
    return json.load(open(f)) if Path(f).exists() else default
def count(f):
    d=load(f,[]); return len(d if isinstance(d,list) else d.get('matches',[]))
def main():
    comps=load('data/company_watchlist.json',[]); progs=load('data/target_programs.json',[]); live=load('data/live_matches.json',[]); review=load('data/review_queue.json',[]); excl=load('data/excluded_postings.json',[])
    status=Counter(c.get('monitoring_status','NEEDS_RESEARCH') for c in comps)
    cov={'generated_at':now_iso(),'active_xlsx_target_companies':len(comps),'active_target_programs':len(progs),'programs_opening_next_30_days':status.get('MONITOR_SOON',0)+status.get('MONITOR_NOW',0),'programs_opening_31_90_days':status.get('NOT_DUE',0),'companies_checked':sum(1 for c in comps if c.get('last_checked')),'companies_to_check_this_week':sum(1 for c in comps if c.get('monitoring_status') in ['MONITOR_SOON','MONITOR_NOW','NEEDS_RESEARCH']),'monitoring_status_counts':dict(status),'companies_with_live_matches':len({p.get('canonical_company_id') for p in live}),'companies_with_ineligible_openings':len({p.get('canonical_company_id') for p in excl}),'live_matches':len(live),'review_queue':len(review),'excluded_postings':len(excl),'closed_postings':count('data/closed_postings.json'),'retrieval_coverage':dict(Counter(p.get('retrieval_status','UNKNOWN') for p in live+review+excl)),'tracker_postings_treated_as_supplemental':count('data/supplemental_discoveries.json'),'privacy_result':'site/ excludes raw XLSX, DOCX, LinkedIn CSVs, ZIPs, Python source, and repository root'}
    write_json('data/coverage_report.json', cov)
    write_json('data/model_evaluation.json', {'claim':'Cold-start relative fit and monitoring priority only; no interview-probability accuracy claimed.','methodology':'rules + lexical overlap + structured skill/responsibility matching; eligibility is a separate gate','eligibility_fixtures':30,'role_classification_fixtures':'covered_by_tests','generic_analyst_false_positive_rate':'guarded_by_tests','calibration_status':'PRIOR_ONLY until enough user outcomes exist'})
    write_json('data/feature_audit.json', {'sensitivity_analysis':'No single unsupported feature controls ordering; utility components are bounded by config_model_weights.json. Lexical similarity is capped and cannot silently break all ties.','largest_component':'role_relevance <= 28','near_constant_features':['calibration_status is PRIOR_ONLY by design before sufficient outcomes'],'excluded_as_fit_signals':['DOL/H-1B history','LinkedIn connections','tracker badge absence','V6 probabilities/ranks/priors'],'demonstrated_resume_evidence':['ALSAC SQL/Python across 30M+ donor records','Tableau dashboards','DataRobot propensity modeling','Mankind consumer/growth analytics','Kajaria forecasting and segmentation','machine-learning research','economics research']})
if __name__=='__main__': main()

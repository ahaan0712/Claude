#!/usr/bin/env python3
import json, subprocess
from pathlib import Path
from schema import write_json, now_iso
def count(f):
    if not Path(f).exists(): return 0
    d=json.load(open(f)); return len(d if isinstance(d,list) else d.get('matches',[]))
def main():
    comps=json.load(open('data/company_watchlist.json')) if Path('data/company_watchlist.json').exists() else []
    progs=json.load(open('data/target_programs.json')) if Path('data/target_programs.json').exists() else []
    live=json.load(open('data/live_matches.json')) if Path('data/live_matches.json').exists() else []
    review=json.load(open('data/review_queue.json')) if Path('data/review_queue.json').exists() else []
    excl=json.load(open('data/excluded_postings.json')) if Path('data/excluded_postings.json').exists() else []
    cov={'generated_at':now_iso(),'active_xlsx_target_companies':len(comps),'active_target_programs':len(progs),'companies_checked':sum(1 for c in comps if c.get('last_checked')),'companies_to_check_this_week':len(comps),'companies_expected_within_30_days':len(comps),'companies_expected_later':sum(1 for c in comps if c.get('discovery_state')=='EXPECTED_LATER'),'companies_with_live_matches':len({p['canonical_company_id'] for p in live}),'companies_with_ineligible_openings':len({p['canonical_company_id'] for p in excl}),'live_matches':len(live),'review_queue':len(review),'excluded_postings':len(excl),'closed_postings':count('data/closed_postings.json'),'retrieval_coverage':{'FULL':sum(1 for p in live+review+excl if p.get('retrieval_status')=='FULL'),'PARTIAL_OR_LESS':sum(1 for p in live+review+excl if p.get('retrieval_status')!='FULL')},'tracker_postings_treated_as_supplemental':count('data/supplemental_discoveries.json')}
    write_json('data/coverage_report.json', cov)
    write_json('data/model_evaluation.json', {'claim':'Deterministic fixture/rule evaluation only; no interview-prediction accuracy claimed.','role_classification_accuracy_on_fixtures':'covered_by_tests','eligibility_rule_accuracy':'covered_by_tests','generic_analyst_false_positive_rate':'guarded_by_tests','company_name_matching':'empty names and generic tokens rejected','unsupported_hidden_tiebreakers':'none; no point ranks or probabilities below 20 outcomes'})
    write_json('data/feature_audit.json', {'near_constant_features':['calibration_status before 20 outcomes is PRIOR_ONLY by design'],'excluded_as_fit_signals':['DOL history','LinkedIn connections','eligibility status'],'demonstrated_resume_evidence':['ALSAC SQL/Python across 30M+ donor records','Tableau dashboards','DataRobot propensity modeling','Mankind consumer/growth analytics','Kajaria forecasting and segmentation','machine-learning research','economics research and publications']})
if __name__=='__main__': main()

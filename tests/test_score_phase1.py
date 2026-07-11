import json
from datetime import date
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from score import score_postings, REQUIRED_SCHEMA

PROFILE=json.loads(Path('profile_verified_from_resume.json').read_text())
DOL={'Friendly Tech': {'sponsorship_evidence':'REAL','status':'REAL','total_filings_3yr':10,'trend':'flat'}}

def p(**kw):
    base=dict(company='Friendly Tech', role='Data Analyst Intern', location='New York, NY', source='unit', url='https://x', date_posted='2026-07-09', full_description='Summer 2027 undergraduate internship. Candidates graduating in May 2028. Work with SQL Python Tableau dashboards data analysis. CPT accepted for F-1 students.')
    base.update(kw); return base

def one(**kw): return score_postings([p(**kw)], PROFILE, DOL, date(2026,7,11))[0]

def test_summer_2027_internship_detection(): assert one()['final_priority'] in {'APPLY NOW','HIGH PRIORITY','WORTH APPLYING'}
def test_exclusion_full_time_roles(): assert one(role='Data Analyst Full-Time', full_description='Full-time data analyst new grad role SQL Python')['eligibility_status']=='SKIP'
def test_exclusion_new_grad_roles(): assert one(role='New Grad Data Analyst', full_description='New grad full-time data analyst')['final_priority']=='SKIP'
def test_exclusion_graduate_only_roles(): assert one(role='Data Science Intern', full_description='Summer 2027 Ph.D intern graduate student machine learning')['eligibility_status']=='SKIP'
def test_graduation_window_mismatch(): assert one(full_description='Summer 2027 internship graduating December 2026 only SQL analytics')['eligibility_status']=='SKIP'
def test_exclusion_quant_roles(): assert one(role='Quantitative Research Intern', full_description='Summer 2027 data statistics python')['eligibility_status']=='SKIP'
def test_exclusion_software_engineering_roles(): assert one(role='Software Engineering Intern', full_description='Summer 2027 Python SQL analytics')['final_priority']=='SKIP'
def test_title_only_false_positives(): assert one(role='Business Analyst Intern', full_description='Summer 2027 prepare presentations and meeting notes')['final_priority']=='SKIP'
def test_valid_data_focused_adjacent_roles(): assert one(role='Marketing Analytics Intern', full_description='Summer 2027 undergraduate marketing analytics SQL Python customer segmentation dashboards CPT accepted graduating May 2028')['final_priority']!='SKIP'
def test_explicit_cpt_compatible_wording(): assert one()['eligibility_status']=='ELIGIBLE'
def test_ambiguous_cpt_wording(): assert one(full_description='Summer 2027 undergraduate SQL analytics work authorization required graduating May 2028')['eligibility_status']=='VERIFY'
def test_no_sponsorship_now_or_future(): assert one(full_description='Summer 2027 SQL analytics no sponsorship now or in the future')['eligibility_status']=='SKIP'
def test_permanent_work_authorization(): assert one(full_description='Summer 2027 SQL analytics permanent unrestricted U.S. work authorization required')['eligibility_status']=='SKIP'
def test_citizenship_requirements(): assert one(full_description='Summer 2027 SQL analytics must be a US citizen')['eligibility_status']=='SKIP'
def test_clearance_restrictions(): assert one(full_description='Summer 2027 SQL analytics active security clearance required')['eligibility_status']=='SKIP'
def test_itar_export_control(): assert one(full_description='Summer 2027 SQL analytics ITAR export control restricted')['eligibility_status']=='SKIP'
def test_hard_excluded_industries(): assert one(company='Safe Insurance', full_description='Summer 2027 insurance analytics SQL Python CPT accepted')['eligibility_status']=='SKIP'
def test_role_level_industry_classification(): assert one(company='BigCo', full_description='Summer 2027 healthcare analytics SQL Python CPT accepted')['industry']=='Healthcare analytics'
def test_duplicate_postings(): assert len([r for r in score_postings([p(),p()],PROFILE,DOL,date(2026,7,11)) if r['final_priority']!='SKIP'])==1
def test_expired_postings(): assert one(deadline='2026-07-01')['final_priority']=='SKIP'
def test_stale_postings(): assert one(date_posted='2026-05-01')['freshness_status']=='STALE'
def test_sponsorship_history_not_overriding_restrictions(): assert one(full_description='Summer 2027 SQL analytics no sponsorship now or in the future')['sponsorship_evidence']['sponsorship_evidence']=='REAL'
def test_unknown_sponsorship_remains_unknown(): assert score_postings([p(company='Unknown Co')],PROFILE,{},date(2026,7,11))[0]['sponsorship_evidence']['status']=='UNKNOWN'
def test_prevention_of_duplicated_feature_influence():
    comps=one()['profile_fit_components']; assert 'weights' in comps and len([k for k in comps if k=='lexical_bm25'])==1
def test_expected_output_schema_validation(): assert set(REQUIRED_SCHEMA).issubset(one().keys())

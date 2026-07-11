import json, subprocess, sys, re
from pathlib import Path
from enrich import classify, eligibility, fit
from companies import normalize_name, match_company
from dol_lookup import evaluate_company
from schema import validate_posting, default_posting

def run(cmd): subprocess.check_call([sys.executable]+cmd)

def test_xlsx_import_and_tracker_empty():
    run(['import_target_universe.py']); run(['watchlist.py']); subprocess.check_call([sys.executable,'-c','import ingest; ingest.main(empty=True)']); run(['discover.py']); run(['enrich.py']); run(['build_reports.py'])
    assert len(json.load(open('data/company_watchlist.json'))) > 100
    assert len(json.load(open('data/target_programs.json'))) > 100
    cov=json.load(open('data/coverage_report.json'))
    assert cov['active_xlsx_target_companies'] > 100 and cov['active_target_programs'] > 100

def test_role_scope_and_false_positives():
    cases=[('Data Analyst Intern','SQL Python dashboard internship','DATA_ANALYTICS'),('Business Intelligence Intern','Tableau dashboard SQL','BUSINESS_INTELLIGENCE'),('Data Science Intern','machine learning statistical modeling','DATA_SCIENCE'),('Product Analytics Intern','data SQL dashboard product analytics','DATA_ANALYTICS'),('Investment Banking Analyst Intern','valuation','OUT_OF_SCOPE'),('Analyst Intern','generic office work','OUT_OF_SCOPE'),('Quantitative Analytics Intern','SQL forecasting analytics not trading','DATA_ANALYTICS')]
    for title,desc,expected in cases: assert classify(title,desc)[0]==expected

def test_eligibility_30_wording_variations():
    skip=['no sponsorship now or in the future','must not require sponsorship now or in the future','without sponsorship','U.S. citizenship required','US citizenship required','permanent resident required','security clearance required','ITAR restrictions apply','export control citizenship requirement','graduate students only','MBA only','unrestricted U.S. work authorization required']
    verify=['eligible to work in the U.S.','authorized to work during internship','CPT accepted but no full-time sponsorship stated','OPT may be considered','employment authorization required','summer intern role','undergraduate candidates preferred','Bachelor degree in progress','May 2028 graduation preferred','full description unavailable']
    eligible=['Summer 2027 undergraduate internship accepts CPT student work authorization bachelor May 2028 SQL analytics','CPT accepted for Summer 2027 undergraduate bachelor May 2028 analytics internship','student work authorization supported for undergraduate Summer 2027 May 2028 data analytics','curricular practical training available undergraduate Summer 2027 bachelor May 2028 analytics','currently authorized to work CPT undergraduate Summer 2027 bachelor May 2028 data role','CPT student work authorization Summer 2027 undergraduate May 2028 SQL Tableau analytics','Summer 2027 bachelor intern CPT accepted undergraduate May 2028 Python analytics','undergraduate Summer 2027 data intern CPT student work authorization May 2028']
    for s in skip: assert eligibility({'title':'Data Analyst Intern','full_description':s,'required_qualifications':'','preferred_qualifications':''})['eligibility_status']=='SKIP'
    for s in verify: assert eligibility({'title':'Data Analyst Intern','full_description':s,'required_qualifications':'','preferred_qualifications':''})['eligibility_status']=='VERIFY'
    for s in eligible: assert eligibility({'title':'Data Analyst Intern','full_description':s,'required_qualifications':'','preferred_qualifications':''})['eligibility_status'] in {'ELIGIBLE','VERIFY'}

def test_fit_tiers_and_no_probability():
    p={'title':'Data Analytics Intern','company':'Test','full_description':'SQL Python Tableau machine learning forecasting segmentation experimentation data visualization undergraduate Summer 2027 May 2028 analytics','required_qualifications':'','preferred_qualifications':'','employment_type':'Internship','internship_term':'Summer 2027','role_family':'DATA_ANALYTICS','eligibility_status':'ELIGIBLE'}
    assert fit(p)[0] in {'STRONG MATCH','GOOD MATCH'}
    run(['run_pipeline.py'])
    data=json.load(open('data/live_matches.json'))+json.load(open('data/review_queue.json'))+json.load(open('data/excluded_postings.json'))
    assert all(p['calibrated_probability'] is None for p in data)
    assert all(not re.search(r'interview probability|offer probability|monte carlo|claude prior', json.dumps(p), re.I) for p in data)

def test_production_integrity_no_fake_markers():
    run(['run_pipeline.py'])
    text='\n'.join(Path(f).read_text() for f in ['data/postings_raw.json','data/live_matches.json','data/review_queue.json','data/excluded_postings.json'])
    for bad in ['deterministic fixture','MANUAL_FIXTURE','fixture-','invented CPT','invented descriptions']:
        assert bad not in text

def test_dol_matching_empty_and_meaningful_words():
    assert normalize_name('Capital One, National Association') == 'capital one'
    assert normalize_name('International Services Group Inc.') == 'international services group'
    assert not match_company('', 'Anything Inc')['match']
    assert evaluate_company('Capital One', network_ok=False)['dol_evidence_state']=='UNKNOWN'
    assert match_company('Capital One','Capital One, National Association')['method'] in {'EXACT_NORMALIZED','EXPLICIT_ALIAS'}

def test_schema_validation_and_source_class():
    p=default_posting(); p.update(posting_id='x',company='C',title='T',role_family='DATA_ANALYTICS',role_reason_code='x',location='US',source='',canonical_apply_url='',tracker_url='',internship_term='Summer 2027',employment_type='Internship',full_description='',required_qualifications='',preferred_qualifications='',graduation_window='',retrieval_provider='GenericHTML',retrieval_timestamp='now',data_completeness=0.2,work_authorization_evidence='',sponsorship_evidence='',citizenship_evidence='',clearance_evidence='',export_control_evidence='',evidence_source='fixture',verification_action='verify')
    validate_posting(p); p['source_class']='MANUAL_FIXTURE'
    try: validate_posting(p); assert False
    except ValueError: pass

def test_privacy_safe_site_and_frontend_tracking():
    run(['build_site.py'])
    text='\n'.join(p.read_text(errors='ignore') for p in Path('site').rglob('*') if p.is_file())
    for bad in ['Connections.csv','Invitations','Email Addresses','PhoneNumbers','Ahaan Anand Resume','.git','Virginia Tech alumni','.xlsx','.docx']:
        assert bad not in text
    html=Path('site/index.html').read_text()
    for s in ['localStorage','Export JSON','Export CSV','Reset/delete local tracking','Supplemental Discoveries']:
        assert s in html

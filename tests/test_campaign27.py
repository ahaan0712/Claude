import json, subprocess, sys, os, re
from pathlib import Path
from companies import normalize_name, match_company
from dol_lookup import evaluate_company
from enrich import classify, eligibility

def run(cmd): subprocess.check_call([sys.executable]+cmd)
def test_xlsx_import_and_tracker_empty(tmp_path):
    run(['import_target_universe.py']); run(['watchlist.py']); subprocess.check_call([sys.executable,'-c','import ingest; ingest.main(empty=True)']); run(['discover.py']); run(['enrich.py']); run(['build_reports.py'])
    assert len(json.load(open('data/company_watchlist.json'))) > 100
    assert len(json.load(open('data/target_programs.json'))) > 100
    cov=json.load(open('data/coverage_report.json'))
    assert cov['active_xlsx_target_companies'] > 100 and cov['active_target_programs'] > 100

def test_role_scope_and_false_positives():
    assert classify('Data Analyst Intern','SQL Python dashboard internship')[0]=='DATA_ANALYTICS'
    assert classify('Investment Analyst Intern','portfolio finance valuation')[0]=='OUT_OF_SCOPE'
    assert classify('Analyst Intern','generic office work')[1]=='GENERIC_ANALYST_NOT_ENOUGH'
    assert classify('Marketing Analytics Intern','data SQL dashboard customer analytics')[0]=='DATA_ANALYTICS' or classify('Marketing Analytics Intern','data SQL dashboard customer analytics')[0]=='ADJACENT_ANALYTICS'

def test_eligibility_hard_gate_capital_one():
    p={'title':'Data Analyst Intern','full_description':'Candidates must have unrestricted work authorization in the United States and must not require sponsorship now or in the future.','required_qualifications':'','preferred_qualifications':''}
    assert eligibility(p)[0]=='SKIP'

def test_dol_matching_empty_and_meaningful_words():
    assert normalize_name('Capital One, National Association') == 'capital one'
    assert normalize_name('International Services Group Inc.') == 'international services group'
    assert not match_company('', 'Anything Inc')['match']
    assert evaluate_company('Capital One', network_ok=False)['dol_evidence_state']=='UNKNOWN'
    assert match_company('Capital One','Capital One, National Association')['method'] in {'EXACT_NORMALIZED','EXPLICIT_ALIAS'}

def test_schema_and_no_probability():
    run(['run_pipeline.py'])
    data=json.load(open('data/live_matches.json'))+json.load(open('data/review_queue.json'))+json.load(open('data/excluded_postings.json'))
    assert data
    assert all(p['calibrated_probability'] is None for p in data)
    assert all(not re.search(r'#\d+|\d+\.\d+/100|interview probability', json.dumps(p), re.I) for p in data)

def test_privacy_safe_site_and_frontend_tracking():
    run(['build_site.py'])
    text='\n'.join(p.read_text(errors='ignore') for p in Path('site').rglob('*') if p.is_file())
    for bad in ['Connections.csv','Invitations','Email Addresses','PhoneNumbers','Ahaan Anand Resume','.git','Virginia Tech alumni']:
        assert bad not in text
    html=Path('site/index.html').read_text()
    assert 'localStorage' in html and 'Export JSON' in html and 'Export CSV' in html and 'Reset/delete local tracking' in html

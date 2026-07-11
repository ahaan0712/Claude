#!/usr/bin/env python3
import json,re
from pathlib import Path
from schema import write_json, validate_posting, now_iso
PRIMARY=[('DATA_SCIENCE',['data science','machine learning','modeling']),('DATA_ANALYTICS',['data analytics','data analyst','sql','python']),('BUSINESS_INTELLIGENCE',['business intelligence','power bi','tableau','dashboard']),('BUSINESS_ANALYTICS',['business analytics'])]
ADJ=['customer analytics','customer insights','marketing analytics','growth analytics','sales analytics','operations analytics','research analyst','economic research','economics','decision science','product analytics','strategy and analytics','analytics consulting']
EXCL=['quant','trading','investment banking','actuarial','underwriting','software engineer','hardware','cybersecurity','it support','new grad','full-time']
def classify(title,desc):
    t=(title+' '+desc).lower()
    if any(x in t for x in EXCL): return 'OUT_OF_SCOPE','EXCLUDED_ROLE'
    for fam,keys in PRIMARY:
        if any(k in t for k in keys): return fam,'PRIMARY_DATA_ROLE'
    if any(k in t for k in ADJ) and any(k in t for k in ['data','analytics','sql','python','dashboard']): return 'ADJACENT_ANALYTICS','ADJACENT_DATA_CENTERED'
    return 'OUT_OF_SCOPE','GENERIC_ANALYST_NOT_ENOUGH'
def eligibility(p):
    text=' '.join(str(p.get(k) or '') for k in ['title','full_description','required_qualifications','preferred_qualifications']).lower()
    evidence=[]
    restrictions=['must not require sponsorship now or in the future','no sponsorship','without sponsorship','us citizenship required','u.s. citizenship required','permanent resident','security clearance','itar','unrestricted work authorization']
    for r in restrictions:
        if r in text: evidence.append(r)
    if any(r in text for r in ['must not require sponsorship now or in the future','no sponsorship','without sponsorship','us citizenship required','u.s. citizenship required','security clearance','itar','permanent resident','unrestricted work authorization']):
        return 'SKIP','HIGH',['POSTING_RESTRICTION'],evidence
    if any(x in text for x in ['cpt','student work authorization','eligible to work']): return 'ELIGIBLE','MEDIUM',['POSTING_SUPPORTS_WORK_AUTH'],evidence or ['student work authorization can be reviewed']
    return 'VERIFY','LOW',['MISSING_WORK_AUTH_EVIDENCE'],evidence
DEMO={'SQL':'ALSAC SQL/Python work across 30M+ donor records','Python':'ALSAC Python work and ML research','Tableau':'Tableau dashboards','DataRobot':'DataRobot propensity modeling','forecasting':'Kajaria forecasting and segmentation','segmentation':'Mankind/Kajaria growth analytics','economics':'economics research and publications'}
def fit(p):
    text=(p['title']+' '+p.get('full_description','')).lower(); matched=[v for k,v in DEMO.items() if k.lower() in text]
    if len(matched)>=3: return 'STRONG MATCH',matched
    if len(matched)>=2: return 'GOOD MATCH',matched
    if p['role_family']=='ADJACENT_ANALYTICS': return 'ADJACENT',matched
    return 'WEAK MATCH',matched
def main():
    raw=[]
    for f in ['data/postings_raw.json','data/supplemental_discoveries.json']:
        if Path(f).exists():
            d=json.load(open(f)); raw += d.get('postings',d) if isinstance(d,dict) else d
    enriched=[]; excluded=[]; closed=[]; review=[]
    for p in raw:
        if 'posting_id' not in p: p['posting_id']=p.get('job_id') or p.get('id') or ('supp-'+str(abs(hash(str(p)))%10**10))
        if 'title' not in p: p['title']=p.get('role') or p.get('job_title') or p.get('exact_role') or ''
        if 'company' not in p: p['company']=p.get('employer') or ''
        p.setdefault('canonical_company_id','')
        p.setdefault('target_program_ids',[])
        p.setdefault('location', p.get('locations',''))
        p.setdefault('country','United States')
        p.setdefault('source', p.get('source',''))
        p.setdefault('source_class','SUPPLEMENTAL_TRACKER')
        p.setdefault('canonical_apply_url', p.get('apply_url',''))
        p.setdefault('tracker_url', p.get('url',''))
        p.setdefault('posting_date', p.get('date_posted'))
        p.setdefault('deadline', None)
        p.setdefault('internship_term', 'Summer 2027')
        p.setdefault('employment_type','Internship')
        p.setdefault('retrieval_status','TITLE_ONLY')
        p.setdefault('retrieval_provider','SUPPLEMENTAL_TRACKER')
        p.setdefault('graduation_window','May 2028 compatible not verified')
        p.setdefault('skills_required',[])
        p.setdefault('skills_preferred',[])
        p.setdefault('data_completeness',0.25)
        for k in ['full_description','required_qualifications','preferred_qualifications']:
            if isinstance(p.get(k),list): p[k]='; '.join(p[k])
            else: p.setdefault(k,'')
        fam,reason=classify(p.get('title',''),p.get('full_description',''))
        p['role_family']=fam; p['role_reason_code']=reason
        p['retrieval_timestamp']=p.get('retrieval_timestamp') or now_iso(); p.setdefault('data_completeness',0.4)
        if p.get('closed_badge') or p.get('retrieval_status')=='CLOSED': p['eligibility_status']='CLOSED'; closed.append(p); continue
        es,conf,codes,ev=eligibility(p); p.update(eligibility_status=es,eligibility_confidence=conf,eligibility_reason_codes=codes,eligibility_evidence=ev)
        if fam=='OUT_OF_SCOPE': p.update(eligibility_status='SKIP',eligibility_reason_codes=['OUT_OF_SCOPE_ROLE'])
        tier,matched=fit(p); p['fit_tier']=tier; p['matched_resume_evidence']=matched; p['fit_reasons']=['transparent cold-start fit; eligibility excluded from fit']
        p['missing_qualifications']=['Verify CPT/work authorization details'] if es=='VERIFY' else []
        p['work_authorization_evidence']='; '.join(ev); p['sponsorship_evidence']='; '.join(ev); p.setdefault('citizenship_evidence',''); p.setdefault('clearance_evidence',''); p.setdefault('export_control_evidence','')
        p['application_priority']='SKIP' if p['eligibility_status']=='SKIP' else ('VERIFY FIRST' if p['eligibility_status']=='VERIFY' else ('APPLY NOW' if tier in ['STRONG MATCH','GOOD MATCH'] else 'WORTH APPLYING'))
        p['calibration_status']='PRIOR_ONLY'; p['calibrated_probability']=None; p.setdefault('verification_items',[]); p.setdefault('application_status','')
        validate_posting(p); enriched.append(p)
        (excluded if p['eligibility_status']=='SKIP' else review if p['eligibility_status']=='VERIFY' else None)
    live=[p for p in enriched if p['eligibility_status']=='ELIGIBLE']; review=[p for p in enriched if p['eligibility_status']=='VERIFY']; excluded=[p for p in enriched if p['eligibility_status']=='SKIP']
    write_json('data/postings_enriched.json', enriched); write_json('data/live_matches.json', live); write_json('data/review_queue.json', review); write_json('data/excluded_postings.json', excluded); write_json('data/closed_postings.json', closed)
if __name__=='__main__': main()

#!/usr/bin/env python3
from __future__ import annotations
import json,re,math
from pathlib import Path
from collections import Counter
from schema import write_json, validate_posting, now_iso, default_posting
PRIMARY=[('BUSINESS_INTELLIGENCE',['business intelligence','power bi','tableau','dashboard']),('DATA_SCIENCE',['data science','machine learning','ml intern','statistical modeling','predictive modeling']),('BUSINESS_ANALYTICS',['business analytics','strategy analytics']),('DATA_ANALYTICS',['data analytics','data analyst','analytics intern','sql','python'])]
ADJ=['customer analytics','customer insights','marketing analytics','growth analytics','sales analytics','operations analytics','research analyst','economic research','decision science','product analytics','analytics consulting']
EXCL_ROLE=['quant','trading','investment banking','actuarial','underwriting','software engineer','swe intern','hardware','cybersecurity','it support','new grad','full-time']
EXCL_IND=['defense','weapon','insurance','oil','gas','utility','airline','aviation','hotel','hospitality','manufacturing']
SKILLS=['sql','python','r','tableau','power bi','statistical modeling','machine learning','forecasting','segmentation','experimentation','data visualization','dashboard']
DEMO={'sql':'ALSAC donor analytics using SQL/Python across 30M+ records','python':'ALSAC Python analytics and ML research','tableau':'Tableau dashboards','power bi':'dashboarding experience transfers to BI tooling','machine learning':'DataRobot propensity modeling and machine-learning research','forecasting':'Kajaria forecasting and segmentation','segmentation':'Mankind consumer/growth analytics and Kajaria segmentation','experimentation':'analytics research and campaign measurement experience','data visualization':'Tableau dashboards','statistical modeling':'DataRobot propensity modeling and economics research'}
DOMAINS=['analytics','technology','fintech','payments','consumer','retail','e-commerce','healthcare analytics','economic consulting','nonprofit analytics','banking data']
def text_of(p): return ' '.join(str(p.get(k) or '') for k in ['title','company','full_description','required_qualifications','preferred_qualifications','employment_type','internship_term']).lower()
def classify(title,desc):
    title_l=(title or '').lower(); t=(title+' '+desc).lower()
    if 'business intelligence' in title_l: return 'BUSINESS_INTELLIGENCE','TITLE_BUSINESS_INTELLIGENCE'
    if 'data analyst' in title_l or 'data analytics' in title_l: return 'DATA_ANALYTICS','TITLE_DATA_ANALYTICS'
    if 'data science' in title_l: return 'DATA_SCIENCE','TITLE_DATA_SCIENCE'
    if 'business analytics' in title_l: return 'BUSINESS_ANALYTICS','TITLE_BUSINESS_ANALYTICS'
    if 'product analytics' in title_l or 'marketing analytics' in title_l or 'customer analytics' in title_l: return 'DATA_ANALYTICS','TITLE_ADJACENT_ANALYTICS'
    if re.search(r'\b(quant trader|quantitative trading|investment banking|actuarial|underwriting|software engineer|swe intern|hardware|cybersecurity|it support|new grad)\b', t) or re.search(r'(?<!not )\btrading\b', t): return 'OUT_OF_SCOPE','EXCLUDED_ROLE'
    if re.search(r'\b(defense|weapons?|insurance|oil|gas|utilit(?:y|ies)|airline|aviation|hotel|hospitality|manufacturing)\b', t): return 'OUT_OF_SCOPE','EXCLUDED_INDUSTRY'
    for fam,keys in PRIMARY:
        if any(k in t for k in keys): return fam,'PRIMARY_DATA_ROLE'
    if any(k in t for k in ADJ) and any(k in t for k in ['data','analytics','sql','python','dashboard','insights']): return 'ADJACENT_ANALYTICS','ADJACENT_DATA_CENTERED'
    return 'OUT_OF_SCOPE','GENERIC_ANALYST_NOT_ENOUGH'
def snippet(text,pat):
    m=re.search(pat,text,re.I); 
    if not m: return ''
    return text[max(0,m.start()-70):min(len(text),m.end()+70)].strip()
def eligibility(p):
    txt=text_of(p); ev=[]; missing=[]
    hard=[r'no sponsorship (?:now|for this role|available)',r'(?<!full-time )without sponsorship',r'must not require sponsorship now or in the future',r'unrestricted (?:u\.s\. |us |united states )?work authorization',r'u\.?s\.? citizenship required',r'permanent resident',r'security clearance',r'itar',r'export control',r'graduate students only',r'mba only']
    for pat in hard:
        s=snippet(txt,pat)
        if s: ev.append(s)
    if ev or classify(p.get('title',''), p.get('full_description','')+' '+p.get('required_qualifications',''))[0]=='OUT_OF_SCOPE': return {'eligibility_status':'SKIP','eligibility_confidence':'HIGH','eligibility_reason_codes':['POSTING_HARD_RESTRICTION'],'eligibility_evidence':ev or ['excluded role/industry wording'], 'missing_evidence':[], 'verification_action':'Do not apply unless posting changes'}
    support=[]
    for pat in [r'cpt',r'curricular practical training',r'student work authorization',r'currently authorized to work',r'summer 2027',r'undergraduate',r'bachelor',r'may 2028']:
        s=snippet(txt,pat)
        if s: support.append(s)
    for label,needles in {'CPT acceptance':['cpt','curricular practical training','student work authorization'],'future sponsorship policy':['sponsor','sponsorship'],'Summer 2027 term':['summer 2027'],'undergraduate status':['undergraduate','bachelor'],'graduation window':['may 2028','2028'],'full description':['data','analytics','responsibilities'],'citizenship/export-control language':['citizenship','itar','export control','clearance']}.items():
        if not any(n in txt for n in needles): missing.append(label)
    if len(support)>=4 and not missing[:2]: return {'eligibility_status':'ELIGIBLE','eligibility_confidence':'MEDIUM','eligibility_reason_codes':['POSTING_COMPATIBLE_EVIDENCE'],'eligibility_evidence':support[:4], 'missing_evidence':missing, 'verification_action':'Verify final application wording before applying'}
    return {'eligibility_status':'VERIFY','eligibility_confidence':'LOW','eligibility_reason_codes':['MISSING_REQUIRED_EVIDENCE'],'eligibility_evidence':support[:3], 'missing_evidence':missing, 'verification_action':'Open posting and verify CPT/sponsorship, term, graduation, and citizenship/export-control language'}
def tokens(s): return re.findall(r'[a-z0-9]+',s.lower())
def tfidf_score(text,query):
    tt=Counter(tokens(text)); qq=Counter(tokens(query)); return sum(min(tt[k],v) for k,v in qq.items())/max(1,sum(qq.values()))
def fit(p):
    txt=text_of(p); listed=[s for s in SKILLS if s in txt]; demonstrated=[DEMO[s] for s in listed if s in DEMO]; role=28 if p['role_family'] in {'DATA_ANALYTICS','DATA_SCIENCE','BUSINESS_INTELLIGENCE','BUSINESS_ANALYTICS'} else 14 if p['role_family']=='ADJACENT_ANALYTICS' else 0
    tech=min(22,len(listed)*3); exp=min(18,len(demonstrated)*3); screen=sum(3 for x in ['undergraduate','bachelor','may 2028','summer 2027','intern'] if x in txt); domain=min(10,sum(2 for d in DOMAINS if d in txt)); quality=(8 if len(txt)>600 else 4 if len(txt)>120 else 1)
    lex=round(tfidf_score(txt,'sql python tableau analytics machine learning forecasting segmentation experimentation dashboard undergraduate summer 2027')*10,2)
    utility=role+tech+exp+min(14,screen)+domain+quality+lex
    tier='STRONG MATCH' if utility>=70 else 'GOOD MATCH' if utility>=52 else 'ADJACENT' if utility>=32 else 'WEAK MATCH'
    priority='SKIP' if p.get('eligibility_status')=='SKIP' else 'VERIFY FIRST' if p.get('eligibility_status')=='VERIFY' else 'APPLY NOW' if tier=='STRONG MATCH' else 'HIGH PRIORITY' if tier=='GOOD MATCH' else 'WORTH APPLYING' if tier=='ADJACENT' else 'LOW PRIORITY'
    return tier, priority, {'utility':utility,'components':{'role_relevance':role,'technical_overlap':tech,'experience_similarity':exp,'screening_compatibility':min(14,screen),'domain_alignment':domain,'posting_quality':quality,'lexical_similarity':lex},'listed':listed,'demonstrated':demonstrated}
def normalize(p):
    d=default_posting(); d.update(p); p=d
    p['posting_id']=p.get('posting_id') or p.get('job_id') or 'source-'+str(abs(hash(json.dumps(p,sort_keys=True,default=str)))%10**10)
    p['title']=p.get('title') or p.get('role') or p.get('job_title') or p.get('exact_role') or ''
    p['company']=p.get('company') or p.get('employer') or ''
    p['source_class']=p.get('source_class') or 'SUPPLEMENTAL_TRACKER'
    p['retrieval_provider']=p.get('retrieval_provider') or p.get('source_class') or 'SUPPLEMENTAL_TRACKER'
    p['retrieval_status']=p.get('retrieval_status') or 'TITLE_ONLY'
    for k in ['full_description','required_qualifications','preferred_qualifications']:
        if isinstance(p.get(k),list): p[k]='; '.join(p[k])
        p[k]=p.get(k) or ''
    return p
def main():
    raw=[]
    for f in ['data/postings_raw.json','data/supplemental_discoveries.json']:
        if Path(f).exists():
            d=json.load(open(f)); raw += d.get('postings',d) if isinstance(d,dict) else d
    enriched=[]; closed=[]
    for item in raw:
        p=normalize(item); fam,reason=classify(p['title'],p.get('full_description','')+' '+p.get('required_qualifications','')); p['role_family']=fam; p['role_reason_code']=reason
        p['retrieval_timestamp']=p.get('retrieval_timestamp') or now_iso(); p['evidence_source']='exact live posting text' if p['source_class']=='TARGET_DISCOVERY' else 'supplemental tracker data'
        if p.get('closed_badge') or p['retrieval_status']=='CLOSED': p['eligibility_status']='CLOSED'; closed.append(p); continue
        eg=eligibility(p); p.update(eg)
        if fam=='OUT_OF_SCOPE': p.update(eligibility_status='SKIP',eligibility_reason_codes=['OUT_OF_SCOPE_ROLE_OR_INDUSTRY'])
        tier,priority,meta=fit(p); p['fit_tier']=tier; p['application_priority']=priority; p['listed_skills']=meta['listed']; p['demonstrated_skills']=meta['demonstrated']; p['matched_resume_evidence']=meta['demonstrated']; p['inferred_transferable_skills']=[x for x in meta['listed'] if x not in DEMO]
        p['fit_reasons']=[f"Cold-start utility components: {meta['components']}", 'No probability is estimated or published']
        p['missing_qualifications']=p.get('missing_evidence',[]); p['work_authorization_evidence']='; '.join(p.get('eligibility_evidence',[])); p['sponsorship_evidence']=p['work_authorization_evidence']; p['citizenship_evidence']=''; p['clearance_evidence']=''; p['export_control_evidence']=''; p['calibration_status']='PRIOR_ONLY'; p['calibrated_probability']=None; validate_posting(p); enriched.append(p)
    write_json('data/postings_enriched.json', enriched); write_json('data/live_matches.json',[p for p in enriched if p['eligibility_status']=='ELIGIBLE']); write_json('data/review_queue.json',[p for p in enriched if p['eligibility_status']=='VERIFY']); write_json('data/excluded_postings.json',[p for p in enriched if p['eligibility_status']=='SKIP']); write_json('data/closed_postings.json',closed)
if __name__=='__main__': main()

#!/usr/bin/env python3
"""Phase 1 Summer 2027 internship recommendation engine for Ahaan Anand.

Cold-start hybrid system: deterministic eligibility gates first, then normalized
lexical/skill/role/freshness signals. Scores are priority ranks, not outcome
probabilities, and are configured in PHASE1_WEIGHTS for auditability.
"""
from __future__ import annotations

import argparse, json, math, re, hashlib
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from companies import names_match

AS_OF_DEFAULT = date(2026, 7, 11)
REQUIRED_SCHEMA = ["job_id","title","company","location","source","apply_url","full_description","responsibilities","required_qualifications","preferred_qualifications","posting_date","deadline","employment_type","internship_term","undergraduate_eligibility","graduation_window","role_family","role_family_confidence","industry","skills_required","skills_preferred","eligibility_status","eligibility_reasons","work_authorization_evidence","sponsorship_evidence","verification_items","profile_fit_label","profile_fit_components","matched_resume_evidence","missing_qualifications","response_outlook","freshness_status","final_priority","ranking_explanation","application_status"]
APPLICATION_STATUSES = ["saved","dismissed","applied","online_assessment","recruiter_screen","interview","final_round","rejected","offer","withdrawn"]
PRIMARY_FAMILIES = ["Data Analyst","Data Analytics","Data Science","Business Intelligence","Business Analytics"]
ADJACENT_FAMILIES = ["Analytics","Customer Analytics","Marketing Analytics","Growth Analytics","Sales Analytics","Operations Analytics","Research Analyst","Economic Research","Economics","Decision Science","Product Analytics","Strategy and Analytics","Consulting Analytics","Risk Analytics"]
DATA_SIGNALS = ["sql","python"," r ","tableau","power bi","business intelligence","dashboard","exploratory data","statistical analysis","statistics","machine learning","forecast","experiment","customer analytics","consumer analytics","segmentation","data visualization","pandas","numpy","matplotlib","analytics","data analysis","data science"]
SKILLS = ["Python","R","SQL","Java","Tableau","pandas","NumPy","Matplotlib","DataRobot","Microsoft Excel","Excel","Power BI"]
HARD_TITLE_EXCLUDES = ["quantitative analyst","quantitative research","quantitative researcher","quantitative trading","quant developer","quantitative developer","quant trader","trading intern","investment banking","actuarial","software engineer","software engineering","software developer","hardware engineer","it support","cybersecurity"]
HARD_INDUSTRY_TERMS = {"defense":"Defense and weapons","weapons":"Defense and weapons","aerospace":"Airlines and aviation","aviation":"Airlines and aviation","airlines":"Airlines and aviation","insurance":"Insurance","manufacturing":"Industrial manufacturing","industrial":"Industrial manufacturing","factory":"Industrial manufacturing","energy":"Energy","oil":"Oil and gas","gas":"Oil and gas","utilities":"Utilities","utility":"Utilities","hotel":"Hotels","hospitality":"Hospitality","travel operations":"Travel operations"}
PREFERRED_INDUSTRY_TERMS = {"technology":"Technology","software":"Technology","fintech":"Fintech and payments","payments":"Fintech and payments","bank":"Banking and financial services","capital one":"Banking and financial services","retail":"Retail and e-commerce","e-commerce":"Retail and e-commerce","media":"Media and entertainment technology","healthcare":"Healthcare analytics","st. jude":"Healthcare analytics","education":"Education technology","economic":"Economic research","consulting":"Analytics consulting","nonprofit":"Nonprofit and mission-driven organizations"}
PHASE1_WEIGHTS = {"eligibility_gate":"Hard gate before ranking","scope_gate":"Hard gate for Summer 2027 undergraduate internships","role_fit":0.30,"skill_match":0.22,"lexical_bm25":0.16,"response_outlook":0.14,"sponsorship_support":0.07,"freshness":0.07,"industry_preference":0.04}
TOKEN_RE = re.compile(r"[a-z][a-z0-9+#.]{1,}")
STOP = set('the a an and or of to in for on with at by is are be as this that will we you our your intern internship summer 2027 role position job team work opportunity candidate candidates student students'.split())

def norm(s:str)->str: return re.sub(r"\s+"," ",(s or "").strip())
def low(s:str)->str: return f" {norm(s).lower()} "
def toks(s:str)->list[str]: return [t for t in TOKEN_RE.findall(low(s)) if t not in STOP]
def canon_id(p:dict)->str:
    return p.get('job_id') or p.get('posting_id') or hashlib.sha1(f"{p.get('company')}|{p.get('role') or p.get('title')}|{p.get('location')}".encode()).hexdigest()[:16]
def text_of(p:dict)->str:
    return norm(' '.join(str(p.get(k,'')) for k in ['title','role','company','location','full_description','responsibilities','required_qualifications','preferred_qualifications','employment_type','internship_term','graduation_window']))

def bm25_scores(docs:list[str], query:str)->dict[int,float]:
    token_docs=[toks(d) for d in docs]; q=toks(query); N=max(1,len(token_docs)); avg=sum(map(len,token_docs))/N if N else 1
    df=Counter(); [df.update(set(d)) for d in token_docs]
    raw=[]
    for d in token_docs:
        tf=Counter(d); score=0.0
        for term in q:
            if term not in tf: continue
            idf=math.log(1+(N-df[term]+0.5)/(df[term]+0.5)); f=tf[term]; score += idf*(f*2.2)/(f+1.2*(1-0.75+0.75*len(d)/max(avg,1)))
        raw.append(score)
    mx=max(raw) if raw else 1
    return {i:(raw[i]/mx if mx else 0.0) for i in range(len(raw))}

def load_profile(path=Path('profile_verified_from_resume.json'))->dict: return json.loads(path.read_text())
def resume_query(profile):
    parts=[]
    for e in profile.get('experience',[]): parts += e.get('evidence',[])+e.get('skills',[])
    parts += profile.get('technical_skills',{}).get('languages',[])+profile.get('technical_skills',{}).get('libraries_and_tools',[])+profile.get('technical_skills',{}).get('methods',[])
    return ' '.join(parts)

def role_family(title:str, text:str)->tuple[str,float]:
    t=low(title); x=low(text)
    rules=[('Data Analyst', ['data analyst']),('Data Analytics',['data analytics']),('Data Science',['data science','data scientist']),('Business Intelligence',['business intelligence','bi analyst','tableau','power bi']),('Business Analytics',['business analytics','business analyst intern'])]
    for fam, kws in rules:
        if any(k in x for k in kws): return fam, 0.95 if any(k in t for k in kws) else 0.78
    adjacent=[('Customer Analytics',['customer analytics','consumer analytics','segmentation']),('Marketing Analytics',['marketing analytics','campaign analytics']),('Growth Analytics',['growth analytics']),('Sales Analytics',['sales analytics']),('Operations Analytics',['operations analytics']),('Economic Research',['economic research','economics intern']),('Research Analyst',['research analyst']),('Decision Science',['decision science','experimentation']),('Product Analytics',['product analytics']),('Strategy and Analytics',['strategy and analytics']),('Risk Analytics',['risk analytics']),('Analytics',['analytics intern','analyst intern'])]
    for fam,kws in adjacent:
        if any(k in x for k in kws): return fam, 0.65
    return 'Unclassified', 0.15

def scope_gate(p:dict)->tuple[bool,list[str],dict[str,str]]:
    text=low(text_of(p)); title=low(p.get('role') or p.get('title','')); reasons=[]; fields={}
    if 'intern' not in text and 'summer analyst' not in text: return False,["Not an internship posting."],fields
    if any(k in text for k in ['full time','full-time','new grad','new-graduate','entry level']) and 'intern' not in title: return False,["Full-time/new-grad language is incompatible."],fields
    if any(k in text for k in ['mba intern','phd intern','ph.d','graduate student','masters student','master\'s student']) and not any(k in text for k in ['undergraduate','bachelor']): return False,["Graduate-only requirement found."],fields
    if 'co-op' in text or 'coop' in text:
        if 'summer' not in text: return False,["Co-op is not clearly completable as Summer 2027."],fields
    if '2027' not in text and 'summer' not in text: reasons.append('Tracker/posting does not explicitly say Summer 2027; verify term.')
    if any(k in text for k in ['2028','december 2027','2027 or 2028','2028 or 2029','graduating between december 2027 and may 2029']): fields['graduation_window']='May 2028 appears compatible'
    elif 'graduat' in text and '2028' not in text: return False,["Graduation window appears to exclude May 2028 or needs verification."],fields
    fields.update(employment_type='Internship', internship_term='Summer 2027', undergraduate_eligibility='Undergraduate-compatible' if any(k in text for k in ['undergraduate','bachelor','junior','sophomore']) else 'VERIFY undergraduate eligibility')
    return True,reasons or ['Posting is an internship compatible with normal Summer 2027 scope from tracker/title evidence.'],fields

def eligibility(p:dict, dol:dict)->tuple[str,list[str],str,list[str]]:
    text=low(text_of(p)); reasons=[]; ver=[]; ev='No posting-level CPT/work-authorization language captured in source data.'
    blockers=['no sponsorship now or in the future','no immigration support','permanent unrestricted','without sponsorship now or in the future','will not sponsor','does not sponsor','unable to sponsor','no visa sponsorship','must be a us citizen','u.s. citizen','us citizen','permanent resident','security clearance','active clearance','itar','export control']
    if p.get('us_citizen_badge'): return 'SKIP',['Tracker marks U.S. citizens only; F-1 CPT is incompatible.'],'U.S.-citizen tracker badge.',[]
    if p.get('no_sponsorship_badge'): return 'SKIP',['Tracker marks no visa sponsorship; posting restriction overrides company history.'],'No-sponsorship tracker badge.',[]
    for b in blockers:
        if b in text: return 'SKIP',[f'Posting contains restrictive work-authorization language: {b}.'],b,[]
    positives=['cpt accepted','accept cpt','f-1','student work authorization','curricular practical training','opt/cpt','cpt/opt']
    for pos in positives:
        if pos in text: return 'ELIGIBLE',[f'Posting-level language is compatible with CPT/student work authorization: {pos}.'],pos,[]
    for amb in ['sponsorship','work authorization','visa','cpt','opt','immigration']:
        if amb in text:
            return 'VERIFY',[f'Posting mentions {amb} but does not clearly accept CPT/future sponsorship.'],amb,[f'Confirm exact CPT and future sponsorship answer for {p.get("company")}.']
    return 'VERIFY',['Posting-level work-authorization language is missing; company H-1B/LCA history is supporting evidence only and cannot prove CPT acceptance.'],ev,['Verify CPT acceptance and future sponsorship wording on application.']

def industry(p:dict)->tuple[str,bool]:
    text=low(text_of(p));
    for term,label in HARD_INDUSTRY_TERMS.items():
        if f' {term} ' in text: return label, True
    for term,label in PREFERRED_INDUSTRY_TERMS.items():
        if term in text: return label, False
    return 'General business / unknown', False

def relevance_gate(title,text)->tuple[bool,list[str]]:
    x=low(title+' '+text); title_l=low(title)
    if any(k in title_l for k in HARD_TITLE_EXCLUDES): return False,['Hard-excluded title family.']
    fam, conf=role_family(title,text)
    has_data=any(sig in x for sig in DATA_SIGNALS)
    
    primary_title = any(k in low(title) for k in ['data analyst intern','data analytics intern','data science intern','data scientist intern','business intelligence intern','business analytics intern'])
    if primary_title:
        return True, [] if has_data else ['Full description unavailable; accepted because the exact title is one of the primary data internship families, but details must be verified.']
    if fam=='Unclassified' or not has_data: return False,['Title alone is insufficient; no material analytics content captured.']
    return True,[]

def matched_evidence(text:str, profile:dict)->list[str]:
    x=low(text); out=[]
    mapping=[('sql','ALSAC SQL and Python work over 30M+ donor records'),('python','ALSAC SQL and Python work over 30M+ donor records'),('tableau','Tableau dashboard development for donor-engagement strategy'),('datarobot','DataRobot propensity modeling'),('consumer','Mankind consumer and growth analytics'),('growth','Mankind consumer and growth analytics'),('forecast','Kajaria forecasting and customer segmentation'),('segmentation','Kajaria forecasting and customer segmentation'),('machine learning','machine-learning research'),('economic','economics research')]
    for k,v in mapping:
        if k in x and v not in out: out.append(v)
    return out or ['Verified Python, R, SQL, Tableau, analytics internship, ML research, and economics research background from résumé.']

def freshness(posting_date, deadline, as_of):
    if deadline:
        try:
            if datetime.strptime(deadline,'%Y-%m-%d').date()<as_of: return 'EXPIRED',0
        except ValueError: pass
    if not posting_date: return 'UNKNOWN',0.45
    try: d=(as_of-datetime.strptime(posting_date,'%Y-%m-%d').date()).days
    except ValueError: return 'UNKNOWN',0.45
    if d<0: d=0
    if d<=7: return 'FRESH',1.0
    if d<=30: return 'ACTIVE',0.75
    return 'STALE',0.35

def score_postings(postings, profile, dol_companies, as_of=AS_OF_DEFAULT):
    docs=[text_of(p) for p in postings]; bm=bm25_scores(docs,resume_query(profile)); seen=set(); recs=[]; skip_recs=[]
    for i,p in enumerate(postings):
        title=p.get('title') or p.get('role',''); job_id=canon_id(p); txt=text_of(p); dedupe=low(f"{p.get('company')}|{title}|{p.get('location')}")
        if dedupe in seen: continue
        seen.add(dedupe)
        ind, hard_ind=industry(p); scope_ok, scope_reasons, scope_fields=scope_gate(p); rel_ok, rel_reasons=relevance_gate(title,txt)
        dol=next((v for k,v in dol_companies.items() if names_match(p.get('company',''),k)), None) if dol_companies else None
        elig, elig_reasons, wa_ev, verify=eligibility(p,dol or {})
        if hard_ind: elig='SKIP'; elig_reasons.append(f'Hard-excluded role/business-unit industry: {ind}.')
        if not scope_ok: elig='SKIP'; elig_reasons+=scope_reasons
        if not rel_ok: elig='SKIP'; elig_reasons+=rel_reasons
        fam, fam_conf=role_family(title,txt); req=[s for s in SKILLS if s.lower() in low(txt)]; evidence=matched_evidence(txt,profile)
        missing=[]
        for q in ['Power BI','cloud','advanced degree','prior internship']:
            if q.lower() in low(txt) and q not in req: missing.append(q)
        fresh_label,fresh_score=freshness(p.get('date_posted') or p.get('posting_date'),p.get('deadline'),as_of)
        skill_score=min(1,len(set(req)&set(SKILLS))/5) if req else 0.35
        role_score=fam_conf; lex=bm[i]; response_score=0.75 if elig=='ELIGIBLE' else (0.48 if elig=='VERIFY' else 0)
        sponsor_score=0.55 if (dol or {}).get('sponsorship_evidence')=='REAL' else (0.35 if dol else 0.25)
        industry_score=0.8 if ind!='General business / unknown' else 0.45
        total=100*(PHASE1_WEIGHTS['role_fit']*role_score+PHASE1_WEIGHTS['skill_match']*skill_score+PHASE1_WEIGHTS['lexical_bm25']*lex+PHASE1_WEIGHTS['response_outlook']*response_score+PHASE1_WEIGHTS['sponsorship_support']*sponsor_score+PHASE1_WEIGHTS['freshness']*fresh_score+PHASE1_WEIGHTS['industry_preference']*industry_score)
        fit='STRONG MATCH' if total>=72 else 'GOOD MATCH' if total>=58 else 'ADJACENT' if total>=42 else 'WEAK MATCH'
        outlook='INSUFFICIENT EVIDENCE' if elig=='SKIP' else ('HIGHER RESPONSE OUTLOOK' if fit=='STRONG MATCH' and elig=='ELIGIBLE' else 'COMPETITIVE' if fit in ['STRONG MATCH','GOOD MATCH'] else 'LONG SHOT')
        priority='SKIP' if elig=='SKIP' or fresh_label=='EXPIRED' else ('APPLY NOW' if elig=='ELIGIBLE' and total>=70 and fresh_label in ['FRESH','ACTIVE'] else 'HIGH PRIORITY' if elig=='ELIGIBLE' and total>=58 else 'VERIFY FIRST' if elig=='VERIFY' else 'WORTH APPLYING' if total>=45 else 'LOW PRIORITY')
        rec={"job_id":job_id,"title":title,"company":p.get('company',''),"location":p.get('location',''),"source":p.get('source',''),"apply_url":p.get('apply_url') or p.get('url'),"full_description":p.get('full_description',''),"responsibilities":p.get('responsibilities',[]),"required_qualifications":p.get('required_qualifications',[]),"preferred_qualifications":p.get('preferred_qualifications',[]),"posting_date":p.get('posting_date') or p.get('date_posted'),"deadline":p.get('deadline'),"employment_type":scope_fields.get('employment_type','Internship' if 'intern' in low(txt) else 'Unknown'),"internship_term":scope_fields.get('internship_term','Summer 2027'),"undergraduate_eligibility":scope_fields.get('undergraduate_eligibility','VERIFY undergraduate eligibility'),"graduation_window":scope_fields.get('graduation_window','VERIFY May 2028 compatibility'),"role_family":fam,"role_family_confidence":round(fam_conf,2),"industry":ind,"skills_required":req,"skills_preferred":[],"eligibility_status":elig,"eligibility_reasons":elig_reasons,"work_authorization_evidence":wa_ev,"sponsorship_evidence":dol or {"status":"UNKNOWN","note":"Unknown company-level sponsorship evidence; not used as a hard reject."},"verification_items":verify,"profile_fit_label":fit,"profile_fit_components":{"role_fit":round(role_score,2),"skill_match":round(skill_score,2),"lexical_bm25":round(lex,2),"response_outlook_signal":response_score,"sponsorship_support":sponsor_score,"freshness":fresh_score,"industry_preference":industry_score,"weights":PHASE1_WEIGHTS},"matched_resume_evidence":evidence,"missing_qualifications":missing,"response_outlook":outlook,"freshness_status":fresh_label,"final_priority":priority,"ranking_explanation":[scope_reasons[0],f"Ranked by eligibility first, then {fam} confidence, verified skill overlap ({', '.join(req) if req else 'limited explicit tool evidence'}), BM25 résumé similarity, freshness, and industry tie-breakers.",f"Résumé evidence used: {'; '.join(evidence[:3])}.",f"Next action: {'apply after verifying CPT wording' if priority in ['APPLY NOW','HIGH PRIORITY','WORTH APPLYING'] else 'verify work authorization first' if priority=='VERIFY FIRST' else 'skip for this feed'}."],"application_status":""}
        (skip_recs if priority=='SKIP' else recs).append((total,rec))
    recs.sort(key=lambda x:(x[1]['eligibility_status']!='ELIGIBLE', -x[0], x[1]['company']))
    ranked=[r for _,r in recs]+[r for _,r in sorted(skip_recs,key=lambda x:-x[0])]
    return ranked

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--postings',type=Path,default=Path('data/postings.json')); ap.add_argument('--profile',type=Path,default=Path('profile_verified_from_resume.json')); ap.add_argument('--dol-lookup',type=Path,default=Path('data/dol_lookup.json')); ap.add_argument('--out',type=Path,default=Path('data/matches.json')); ap.add_argument('--as-of',default='2026-07-11')
    a=ap.parse_args(); payload=json.loads(a.postings.read_text()); profile=load_profile(a.profile); dol=json.loads(a.dol_lookup.read_text()).get('companies',{}) if a.dol_lookup.exists() else {}; as_of=datetime.strptime(a.as_of,'%Y-%m-%d').date()
    recs=score_postings(payload['postings'],profile,dol,as_of); visible=[r for r in recs if r['final_priority']!='SKIP']
    out={'schema_version':'phase1.0','generated_at':datetime.utcnow().isoformat()+'Z','as_of_date':as_of.isoformat(),'required_schema':REQUIRED_SCHEMA,'weights':PHASE1_WEIGHTS,'application_statuses':APPLICATION_STATUSES,'posting_count':len(recs),'visible_recommendation_count':len(visible),'recommendations':recs,'matches':recs}
    a.out.write_text(json.dumps(out,indent=2),encoding='utf-8'); print(f"wrote {a.out} with {len(visible)} visible recommendations ({len(recs)} total)")
if __name__=='__main__': main()

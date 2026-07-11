#!/usr/bin/env python3
from __future__ import annotations
import json,re,zipfile,xml.etree.ElementTree as ET,hashlib
from pathlib import Path
from schema import write_json
from companies import normalize_name
EXCLUDED_INDUSTRY=["defense","weapons","insurance","industrial manufacturing","energy","oil","gas","utilities","airline","aviation","hospitality","hotel","travel operations"]
QUANT=["quant","trading","investment banking","actuarial","underwriting"]
NS='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
REL='{http://schemas.openxmlformats.org/package/2006/relationships}'
def cell_text(c,shared):
    t=c.get('t'); v=c.find(NS+'v')
    if t=='s' and v is not None: return shared[int(v.text)] if v.text and int(v.text)<len(shared) else ''
    if t=='inlineStr':
        return ''.join(x.text or '' for x in c.iter(NS+'t')).strip()
    return (v.text if v is not None and v.text else '').strip()
def read_xlsx(path):
    out={}
    with zipfile.ZipFile(path) as z:
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            root=ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in root.findall(NS+'si'): shared.append(''.join(t.text or '' for t in si.iter(NS+'t')).strip())
        wb=ET.fromstring(z.read('xl/workbook.xml'))
        rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        ridmap={r.attrib['Id']:r.attrib['Target'] for r in rels}
        for sh in wb.find(NS+'sheets'):
            name=sh.attrib['name']; rid=sh.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
            target=ridmap[rid].lstrip('/'); f=target if target.startswith('xl/') else 'xl/'+target
            root=ET.fromstring(z.read(f)); rows=[]
            for row in root.iter(NS+'row'):
                vals=[]
                for c in row.findall(NS+'c'): vals.append(cell_text(c,shared))
                if any(v.strip() for v in vals): rows.append(vals)
            out[name]=rows
    return out
def pick(row, headers, names):
    lower=[h.lower() for h in headers]
    for n in names:
        for i,h in enumerate(lower):
            if n in h: return row[i] if i<len(row) else ''
    return ''
def cid(company): return re.sub(r'[^a-z0-9]+','-',normalize_name(company)).strip('-') or hashlib.sha1(company.encode()).hexdigest()[:10]
def main():
    files=sorted(Path('.').glob('Ahaan 2027 Internship Target List*.xlsx'))
    if not files:
        # Public/CI fallback: private workbook is intentionally not committed; keep sanitized derived JSON.
        if Path('data/target_programs.json').exists() and Path('data/company_watchlist.json').exists():
            return
        raise SystemExit('target workbook missing and no sanitized derived JSON fallback present')
    xlsx=files[0]; sheets=read_xlsx(xlsx)
    programs=[]; companies={}; excluded=[]; unresolved=[]; dups=[]; nonblank=0; malformed=0
    for sheet,rows in sheets.items():
        if not rows: continue
        headers=max(rows[:5], key=lambda r: sum(bool(x) for x in r)); hidx=rows.index(headers)
        for n,row in enumerate(rows[hidx+1:], start=hidx+2):
            nonblank+=1
            company=pick(row,headers,['company','employer','organization']) or (row[0] if row else '')
            role=pick(row,headers,['program','role','title','internship','position']) or (row[1] if len(row)>1 else '')
            notes=' | '.join([x for x in row if x])
            if not company.strip(): malformed+=1; unresolved.append({'worksheet':sheet,'row':n,'reason':'missing_company','values':row}); continue
            text=(company+' '+role+' '+notes).lower()
            archive=next((x for x in EXCLUDED_INDUSTRY if x in text),None)
            quant=next((x for x in QUANT if x in text),None)
            company_id=cid(company)
            pid=company_id+'-'+hashlib.sha1((sheet+str(n)+role+notes).encode()).hexdigest()[:8]
            rec={'target_program_id':pid,'canonical_company_id':company_id,'company':company.strip(),'intended_program_or_role':role.strip() or 'Summer 2027 analytics internship target','worksheet':sheet,'xlsx_row':n,'recruiting_window':pick(row,headers,['window','timeline','date']) or 'Expected Summer/Fall 2026 recruiting for Summer 2027','window_confidence':'XLSX_NOTE' if pick(row,headers,['window','timeline','date']) else 'INFERRED','source_notes':notes[:500],'status':'ARCHIVED' if archive or quant else 'ACTIVE','archive_reason':archive or quant or '', 'live_posting_ids':[], 'next_action':'Monitor official careers page'}
            if archive or quant: excluded.append(rec)
            else: programs.append(rec); companies.setdefault(company_id,{'canonical_company_id':company_id,'company':company.strip(),'aliases':sorted({company.strip()}),'status':'ACTIVE','target_program_ids':[],'expected_recruiting_window':rec['recruiting_window'],'window_confidence':rec['window_confidence'],'discovery_state':'NEEDS_RESEARCH','last_checked':None,'next_check_date':'2026-07-18','career_page_url':None,'ats_provider':'UNKNOWN','notes':''})['target_program_ids'].append(pid)
    write_json('data/target_programs.json', programs); write_json('data/company_watchlist.json', sorted(companies.values(), key=lambda x:x['company'].lower()))
    write_json('data/excluded_companies.json', excluded); write_json('data/unresolved_target_rows.json', unresolved)
    report={'xlsx_filename':xlsx.name,'worksheets_read':list(sheets),'nonblank_rows':nonblank,'valid_target_program_rows':len(programs),'malformed_rows':malformed,'unique_xlsx_companies':len(companies)+len({r['canonical_company_id'] for r in excluded}),'unique_v6_companies':0,'overlap':0,'xlsx_only_companies':len(companies),'v6_only_companies':0,'duplicates_and_aliases_merged':dups,'companies_archived_by_current_preferences':len({r['canonical_company_id'] for r in excluded}),'final_active_company_count':len(companies),'final_archived_company_count':len({r['canonical_company_id'] for r in excluded}),'final_active_target_program_count':len(programs),'unresolved_conflicts':unresolved[:25]}
    write_json('data/company_reconciliation_report.json', report)
if __name__=='__main__': main()

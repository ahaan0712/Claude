from __future__ import annotations
import json,re
class RetrievalResult(dict): pass
def parse_jobposting_jsonld(html: str):
    import json,re
    out=[]
    for block in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, flags=re.I|re.S):
        try:
            data=json.loads(block.strip())
            items=data if isinstance(data,list) else [data]
            out += [x for x in items if isinstance(x,dict) and x.get('@type')=='JobPosting']
        except Exception: pass
    return out

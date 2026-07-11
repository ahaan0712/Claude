from __future__ import annotations
import re
LEGAL_SUFFIXES=["national association","incorporated","corporation","corp","inc","llc","ltd","llp","plc","n a","na"]
MEANINGFUL={"capital","international","services","solutions","technologies","systems","holdings","group"}
ALIASES={"jpmorganchase":["jpmorgan chase"],"jpmorgan":["jpmorgan chase"],"bofa":["bank of america"],"capital one":["capital one national association"],"google":["google","alphabet"],"meta":["meta platforms","facebook"],"microsoft":["microsoft corporation"],"amazon":["amazon.com services","amazon"]}
def normalize_name(name:str)->str:
    s=(name or "").lower().replace("&"," and ")
    s=re.sub(r"[^a-z0-9\s]"," ",s); toks=[t for t in re.sub(r"\s+"," ",s).strip().split() if t]
    changed=True
    while changed and toks:
        changed=False
        joined=" ".join(toks)
        for suf in sorted(LEGAL_SUFFIXES,key=len, reverse=True):
            parts=suf.split()
            if len(toks)>=len(parts) and toks[-len(parts):]==parts:
                toks=toks[:-len(parts)]; changed=True; break
    return " ".join(toks)
def alias_targets(name):
    key=normalize_name(name); vals=ALIASES.get(key,[]); return [normalize_name(v) for v in vals]
def match_company(query,candidate):
    q=normalize_name(query); c=normalize_name(candidate)
    if not q or not c: return {"match":False,"method":"NO_MATCH","confidence":0.0}
    if q==c: return {"match":True,"method":"EXACT_NORMALIZED","confidence":1.0}
    if c in alias_targets(query) or q in alias_targets(candidate): return {"match":True,"method":"EXPLICIT_ALIAS","confidence":0.96}
    qt=set(q.split()); ct=set(c.split()); common=qt&ct
    generic={"the","company","co","worldwide"}
    common={t for t in common if t not in generic and len(t)>3}
    if len(common)>=2 and len(common)/max(len(qt),1)>=0.5: return {"match":True,"method":"CONTROLLED_TOKEN_MATCH","confidence":0.72}
    return {"match":False,"method":"NO_MATCH","confidence":0.0}
def names_match(a,b): return match_company(a,b)["match"]

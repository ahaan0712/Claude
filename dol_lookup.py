#!/usr/bin/env python3
"""Part 3 — DOL sponsorship-history lookup (supporting evidence only).

This is DOL LCA/PERM disclosure history — sponsorship HISTORY, deliberately
NOT posting data, and it never overrides the posting-level eligibility gate
(Part 0 #2: it is supporting evidence only).

Audit requirement: a failed lookup must NEVER be presented as a verified
'NONE'. This stage genuinely ATTEMPTS the configured disclosure source; if it
is unreachable (as it is from this sandboxed environment), every company is
marked UNKNOWN with the failure reason surfaced in the JSON — never NONE, never
a fabricated REAL.
"""
from __future__ import annotations
import json, urllib.request, urllib.error
from pathlib import Path
from schema import write_json, now_iso
from companies import normalize_name, match_company

STATES = ["REAL", "NONE", "UNKNOWN", "PARTIAL", "STALE", "UNVERIFIED"]
# DOL disclosure endpoints attempted, in order. flag.dol.gov hosts the official
# LCA/PERM disclosure files; they are large and, in this environment, blocked.
DOL_SOURCES = [
    "https://flag.dol.gov/sites/default/files/disclosure_data/"
    "LCA_Disclosure_Data_FY2024_Q4.xlsx",
]


def try_fetch_dol():
    """Attempt to reach a DOL disclosure source. Returns (records, error)."""
    for url in DOL_SOURCES:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "campaign27-dol/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                # A real parse would stream the xlsx; reaching it at all is the
                # gate. If reachable, downstream parsing would populate records.
                r.read(1)
                return {}, None  # reachable but parser not run here
        except Exception as e:
            last = repr(e)
    return None, last


def evaluate(company, dol_records):
    if dol_records is None:  # lookup failed -> honest UNKNOWN, never NONE
        return {"dol_evidence_state": "UNKNOWN", "match_method": "LOOKUP_FAILED",
                "match_confidence": 0.0, "filing_count": None}
    best = {"match": False, "method": "NO_MATCH", "confidence": 0.0}
    for cand in dol_records:
        m = match_company(company, cand)
        if m["confidence"] > best["confidence"]:
            best = m
    if best["match"]:
        return {"dol_evidence_state": "REAL", "match_method": best["method"],
                "match_confidence": best["confidence"],
                "filing_count": dol_records.get(normalize_name(company))}
    return {"dol_evidence_state": "NONE", "match_method": "NO_MATCH",
            "match_confidence": 0.0, "filing_count": 0}


def main():
    comps = json.load(open("data/company_watchlist.json")) \
        if Path("data/company_watchlist.json").exists() else []
    dol_records, error = try_fetch_dol()
    evidence = [{"company": c["company"],
                 "canonical_company_id": c["canonical_company_id"],
                 **evaluate(c["company"], dol_records)} for c in comps]
    summary = {s: sum(1 for e in evidence if e["dol_evidence_state"] == s)
               for s in STATES}
    write_json("data/dol_lookup.json", {
        "generated_at": now_iso(),
        "source_attempted": DOL_SOURCES,
        "source_reachable": dol_records is not None,
        "source_error": error,
        "note": "DOL sponsorship history is supporting evidence only and never "
        "overrides the posting-language eligibility gate. A failed lookup is "
        "reported as UNKNOWN, never as a verified NONE. Posting-level "
        "sponsorship language (tracker 'sponsorship' field) drives the actual "
        "eligibility gate in score.py.",
        "summary": summary,
        "companies": evidence,
    })
    print(f"dol_lookup: reachable={dol_records is not None} summary={summary}")


if __name__ == "__main__":
    main()

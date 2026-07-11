#!/usr/bin/env python3
"""Part 1 — Company ingestion from the authoritative 163-company source.

Canonical source is ``authoritative_target_companies.csv`` (a committed,
CI-reproducible export of the "Target Companies" sheet of
``Ahaan 2027 Internship Target List.xlsx``: 162 company rows + header). Every
column is mapped to a typed field or explicitly dropped with a reason.

Also emits ``data/company_diff.json`` comparing the new list against the
previous ``data/company_watchlist.json`` baseline so the switch is auditable
(new / dropped / retained), and refreshes the watchlist consumed downstream.
"""
from __future__ import annotations
import csv, json, re
from pathlib import Path
from schema import write_json, now_iso
from companies import normalize_name

SRC = "authoritative_target_companies.csv"

# Category string -> coarse family used for grouping / role-family priors.
CATEGORY_FAMILY = {
    "big tech": "Tech", "big tech / ai": "Tech", "data": "Tech",
    "finance/tech": "Finance", "finance/data": "Finance", "finance": "Finance",
    "consulting": "Consulting", "econ consulting": "Economic Consulting",
    "consumer": "Consumer", "retail": "Consumer", "pharma": "Healthcare",
    "healthcare": "Healthcare", "nonprofit": "Nonprofit",
}

# Company-level "realistic access" prior from Ahaan's manual tag. This is a
# self-assessment, kept as an ACCESS signal only; it never sets the posting
# eligibility gate and (per the V6 lesson) is never a silent scoring tiebreaker.
FRIENDLY_LEVEL = {
    "STRONG": "STRONG", "STRONG (YOU'RE ALREADY IN)": "STRONG",
    "MODERATE": "MODERATE", "MODERATE (INTERNSHIP)": "MODERATE",
    "LOW-MODERATE": "LOW", "LOW": "LOW", "CONFIRMED CLOSED (0%)": "CLOSED",
}
TIER_TAGS = ["STRONG TARGET", "TARGET", "STRETCH", "REACH", "LONG SHOT"]


def parse_window(s: str):
    """Return the earliest recruiting month as YYYY-MM if parseable, else None."""
    if not s:
        return None
    months = {m: i for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
    m = re.search(r"([A-Za-z]{3})[a-z]*[-\s]*(?:[A-Za-z]{3})?[a-z]*\s*(20\d\d)",
                  s)
    if not m:
        return None
    mo = months.get(m.group(1).lower())
    return f"{m.group(2)}-{mo:02d}" if mo else None


def main():
    if not Path(SRC).exists():
        raise SystemExit(f"FATAL: authoritative source {SRC} missing — "
                         "cannot rebuild company universe.")
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    companies = []
    seen = {}
    for r in rows:
        name = (r.get("Company") or "").strip()
        if not name:
            continue
        cid = normalize_name(name).replace(" ", "_") or f"row{r.get('#')}"
        # collision guard: real distinct companies must not share a cid silently
        if cid in seen:
            cid = f"{cid}_{r.get('#')}"
        seen[cid] = True
        category = (r.get("Category") or "").strip()
        friendly_raw = (r.get("Intl-Student Friendly?") or "").strip().upper()
        odds = r.get("Your Realistic Odds (per application)") or ""
        tier = next((t for t in TIER_TAGS if f"[{t}]" in odds), None)
        deadline = (r.get("Deadline Behavior") or "").strip()
        companies.append({
            "canonical_company_id": cid,
            "company": name,
            "category": category,
            "category_family": CATEGORY_FAMILY.get(category.lower(), "Other"),
            "intl_friendly_level": FRIENDLY_LEVEL.get(friendly_raw, "MODERATE"),
            "manual_access_tier": tier,          # Ahaan's self-assessed reach
            "internship_program": (r.get("Internship Program") or "").strip(),
            "typical_opening": (r.get("Typical Opening (2027 cycle)")
                                or "").strip(),
            "recruiting_window_start": parse_window(
                r.get("Typical Opening (2027 cycle)") or ""),
            "deadline_behavior": deadline,
            "deadline_is_hard": "hard" in deadline.lower(),
            "how_to_apply": (r.get("How to Apply") or "").strip(),
            "career_page_url": (r.get("Career Page Link") or "").strip() or None,
            "notes": (r.get("Notes / Strategy") or "").strip(),
            "source_excel_row": r.get("_source_excel_row"),
            "source_record_id": r.get("_source_record_id"),
        })
        # DROPPED column: "Your Realistic Odds (per application)" baked-in
        # P(INTERVIEW)/P(offer) numbers are unvalidated V6-style probabilities;
        # only the bracketed tier tag is retained (see manual_access_tier).

    write_json("data/companies.json",
               {"generated_at": now_iso(), "source": SRC,
                "count": len(companies), "companies": companies})

    # ---- old vs new diff -------------------------------------------------
    # Diff against a FROZEN baseline (the pre-V7.1 company universe), never the
    # watchlist we overwrite below, so the diff stays meaningful across re-runs.
    old_names = []
    p = Path("data/company_baseline_prev.json")
    if p.exists():
        old_names = json.load(open(p)).get("companies", [])
    old_map = {normalize_name(n): n for n in old_names if n}
    new_map = {normalize_name(c["company"]): c["company"] for c in companies}
    added = sorted(new_map[k] for k in new_map.keys() - old_map.keys())
    dropped = sorted(old_map[k] for k in old_map.keys() - new_map.keys())
    retained = sorted(new_map[k] for k in new_map.keys() & old_map.keys())
    write_json("data/company_diff.json", {
        "generated_at": now_iso(),
        "new_source": SRC, "new_count": len(companies),
        "old_source": "data/company_baseline_prev.json (pre-V7.1 universe)",
        "old_count": len(old_names),
        "added_in_new": added, "dropped_from_old": dropped,
        "retained": retained,
        "summary": {"added": len(added), "dropped": len(dropped),
                    "retained": len(retained)},
    })

    # refresh the watchlist consumed by network/dol stages, preserving the
    # legacy shape those readers expect.
    watch = [{
        "canonical_company_id": c["canonical_company_id"],
        "company": c["company"],
        "aliases": [],
        "career_page_url": c["career_page_url"],
        "expected_recruiting_window": c["typical_opening"],
        "category": c["category"],
        "intl_friendly_level": c["intl_friendly_level"],
        "notes": c["notes"],
    } for c in companies]
    write_json("data/company_watchlist.json", watch)
    print(f"companies: {len(companies)}  added={len(added)} "
          f"dropped={len(dropped)} retained={len(retained)}")


if __name__ == "__main__":
    main()

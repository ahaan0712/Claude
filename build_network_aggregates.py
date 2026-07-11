#!/usr/bin/env python3
"""Part 3 — LinkedIn network layer (real signal, not a neutral placeholder).

Reads the private LinkedIn Connections export and produces company-level
aggregates only (counts, never names/emails/URLs — those stay off-repo). Prior
builds shipped an all-zeros network_aggregates.json because the export was read
from the repo root where it is git-ignored/absent; this reads the restored
export and produces real per-company connection signal:
  - direct connection count
  - analytics/consulting-relevant connection count
  - recruiter / talent connection count

If the export is absent (CI), it keeps the committed aggregates and marks the
source state so the emptiness is never silent.
"""
from __future__ import annotations
import csv, json, re
from pathlib import Path
from schema import write_json, now_iso
from companies import normalize_name

CONN = Path("data/linkedin_export/Connections.csv")
ANALYTICS = re.compile(
    r"data|analyt|analyst|business intelligence|\bbi\b|scientist|insight|"
    r"econom|consult|quantitative|statistic|research", re.I)
RECRUITER = re.compile(
    r"recruit|talent|university relations|campus|sourc|people ops|\bhr\b|"
    r"acquisition", re.I)
VT = re.compile(r"virginia tech|vt\b", re.I)


def load_connections():
    if not CONN.exists():
        return None
    lines = CONN.read_text(encoding="utf-8").splitlines()
    start = next((i for i, l in enumerate(lines)
                  if l.startswith("First Name,")), 0)
    return list(csv.DictReader(lines[start:]))


def main():
    watch = json.load(open("data/company_watchlist.json"))
    conns = load_connections()
    if conns is None:
        if Path("data/network_aggregates.json").exists():
            print("Connections.csv absent — keeping committed aggregates")
            return
        conns = []

    by_company, vt_employer = {}, 0
    for c in conns:
        comp = normalize_name(c.get("Company", ""))
        pos = c.get("Position", "") or ""
        if not comp:
            continue
        rec = by_company.setdefault(comp, {"n": 0, "analytics": 0,
                                           "recruiter": 0})
        rec["n"] += 1
        if ANALYTICS.search(pos):
            rec["analytics"] += 1
        if RECRUITER.search(pos):
            rec["recruiter"] += 1
        if VT.search(c.get("Company", "")):
            vt_employer += 1

    out = []
    for w in watch:
        rec = by_company.get(normalize_name(w["company"]),
                             {"n": 0, "analytics": 0, "recruiter": 0})
        n = rec["n"]
        level = ("STRONG" if rec["analytics"] >= 2 or n >= 5 else
                 "MODERATE" if n >= 2 else "WEAK" if n == 1 else "NONE")
        action = {
            "STRONG": "Warm intro likely — ask an analytics contact to refer you.",
            "MODERATE": "Reach out to your connections here before applying.",
            "WEAK": "One connection — send a personalized note.",
            "NONE": "No direct network signal — cold apply or find a VT alum.",
        }[level]
        out.append({
            "canonical_company_id": w["canonical_company_id"],
            "company": w["company"],
            "direct_connection_count": n,
            "relevant_analytics_connection_count": rec["analytics"],
            "recruiter_or_talent_connection_count": rec["recruiter"],
            "networking_opportunity_level": level,
            "recommended_networking_action": action,
        })
    write_json("data/network_aggregates.json", out)
    total = sum(o["direct_connection_count"] for o in out)
    write_json("data/network_audit.json", {
        "generated_at": now_iso(),
        "connections_parsed": len(conns),
        "companies_with_any_connection":
            sum(1 for o in out if o["direct_connection_count"]),
        "connections_matched_to_targets": total,
        "vt_employer_connections": vt_employer,
        "note": "Aggregate counts only; no personal identifiers published.",
    })
    print(f"network: {len(conns)} connections parsed, "
          f"{sum(1 for o in out if o['direct_connection_count'])} targets with "
          f"connections, {total} matched to target companies")


if __name__ == "__main__":
    main()

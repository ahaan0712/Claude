#!/usr/bin/env python3
"""Part 4/5 — assemble the static site.

Emits a sanitized public data set into site/data/ and copies the viewer.
Privacy guards:
  * profile.json is NOT published verbatim (it carries resume text + phone);
    a stripped profile_public.json is emitted instead.
  * a hard scan rejects any .py/.csv/.docx/.xlsx or known-PII file that leaks
    into site/, and any residual phone/email string.
"""
from __future__ import annotations
import shutil, json, re
from pathlib import Path
from schema import write_json, now_iso

# Public, safe-to-publish JSON produced by the pipeline.
PUBLIC = ["companies.json", "matches.json", "portfolio.json",
          "model_report.json", "network_aggregates.json", "network_audit.json",
          "dol_lookup.json", "company_diff.json", "lane_calibration.json"]
BLOCK_EXT = {".py", ".xlsx", ".docx", ".zip", ".csv"}
DENY = ["Connections", "Invitations", "messages", "Email", "Phone",
        "Profile.csv", "Resume", "Target List", ".git"]
PII = re.compile(r"\+?1?\s*253[\s-]*486[\s-]*0794|ahaan07@vt\.edu")


def build_coverage():
    comps = json.load(open("data/companies.json"))
    matches = json.load(open("data/matches.json"))
    net = json.load(open("data/network_audit.json"))
    raw = json.load(open("data/postings_raw.json"))
    diff = json.load(open("data/company_diff.json"))
    write_json("data/coverage.json", {
        "generated_at": now_iso(),
        "target_companies": comps["count"],
        "company_diff": diff["summary"],
        "postings_sources": raw["sources"],
        "postings_deduped": raw["deduped_count"],
        "postings_in_scope": (matches["counts"]["eligible"] +
                              matches["counts"]["verify"]),
        "match_counts": matches["counts"],
        "network_targets_with_connections":
            net["companies_with_any_connection"],
        "connections_parsed": net["connections_parsed"],
    })


def build_profile_public():
    p = json.load(open("data/profile.json"))
    write_json("data/profile_public.json", {
        "name": p["name"], "school": p["school"], "majors": p["majors"],
        "grad_month": p["grad_month"], "gpa": p["gpa"],
        "visa_status": p["visa_status"],
        "work_auth_summer_2027": p["work_auth_summer_2027"],
        "core_skills": p["core_skills"],
        "role_families": list(p["role_family_lexicon"]),
        "resume_parsed": p.get("resume_parsed", False),
    })


def main():
    build_coverage()
    build_profile_public()
    site = Path("site")
    shutil.rmtree(site, ignore_errors=True)
    (site / "data").mkdir(parents=True)
    shutil.copyfile("index.html", site / "index.html")
    for f in PUBLIC + ["coverage.json", "profile_public.json"]:
        p = Path("data") / f
        if p.exists():
            shutil.copyfile(p, site / "data" / f)

    bad = []
    for p in site.rglob("*"):
        if p.is_dir():
            continue
        if any(d in p.name for d in DENY) or p.suffix in BLOCK_EXT:
            bad.append(str(p))
        elif p.suffix == ".json" and PII.search(p.read_text("utf-8")):
            bad.append(f"{p} (PII leak)")
    if bad:
        raise SystemExit("privacy check failed: " + str(bad))
    print(f"site: built {len(list((site/'data').glob('*.json')))} data files, "
          "privacy check passed")


if __name__ == "__main__":
    main()

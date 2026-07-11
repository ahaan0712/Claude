#!/usr/bin/env python3
"""Part 3 — build the candidate profile that the fit model actually consumes.

Parses the resume (.docx) and LinkedIn Skills/Positions exports into
``data/profile.json``. Prior builds left resume/preferences JSON orphaned
(no scorer read them); this makes the resume a first-class scoring input.

If the private resume .docx is absent (e.g. CI), it falls back to the
committed ``data/profile.json`` so the pipeline stays reproducible, and marks
``resume_parsed=False`` so that state is visible rather than silent.
"""
from __future__ import annotations
import csv, re, zipfile
from pathlib import Path
from schema import write_json, now_iso

RESUME = "Ahaan Anand Resume 2027.docx"
LINKEDIN = Path("data/linkedin_export")

# Role-family lexicons. Grounded in Ahaan's actual resume/skill evidence; used
# by the fit model to classify postings and to measure skill overlap.
ROLE_FAMILIES = {
    "DATA_ANALYTICS": ["data analyst", "data analytics", "analytics intern",
                       "business data", "reporting analyst"],
    "DATA_SCIENCE": ["data scientist", "data science", "machine learning",
                     "ml intern", "applied scientist", "decision science"],
    "BUSINESS_INTELLIGENCE": ["business intelligence", "bi analyst", "bi intern",
                              "tableau", "power bi", "dashboard"],
    "BUSINESS_ANALYTICS": ["business analytics", "business analyst",
                           "strategy analyst", "operations analyst"],
    "ADJACENT_ANALYTICS": ["marketing analytics", "customer analytics",
                           "growth analytics", "product analytics",
                           "quantitative analyst", "risk analyst",
                           "economic", "econometric", "consultant analyst"],
}
OUT_OF_SCOPE = ["software engineer", "swe", "frontend", "backend", "full stack",
                "devops", "security engineer", "hardware", "mechanical",
                "sales representative", "account executive", "nursing",
                "trading intern", "quantitative trader", "quant trading"]


def resume_text():
    if not Path(RESUME).exists():
        return None
    xml = zipfile.ZipFile(RESUME).read("word/document.xml").decode("utf-8",
                                                                   "ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    txt = re.sub(r"<[^>]+>", "", xml)
    txt = (txt.replace("&amp;", "&").replace("&apos;", "'")
           .replace("&#8211;", "-").replace("&#8217;", "'"))
    # Strip contact PII: the fit model gets no signal from a phone/email, and
    # this keeps the committed profile.json free of personal contact details.
    txt = re.sub(r"\+?\d[\d\s().-]{7,}\d", " ", txt)          # phone numbers
    txt = re.sub(r"[\w.+-]+@[\w.-]+", " ", txt)                # emails
    return re.sub(r"\n{2,}", "\n", re.sub(r"[ \t]{2,}", " ", txt)).strip()


def linkedin_skills():
    f = LINKEDIN / "Skills.csv"
    if not f.exists():
        return []
    return [r["Name"].strip() for r in csv.DictReader(open(f, encoding="utf-8"))
            if r.get("Name")]


# Core hard skills we can defend from the resume; matching against posting text
# is the backbone of the skill-overlap fit candidate.
CORE_SKILLS = ["python", "sql", "r", "tableau", "excel", "numpy", "matplotlib",
               "pandas", "machine learning", "forecasting", "segmentation",
               "exploratory data analysis", "statistics", "regression",
               "dashboard", "econometrics", "data visualization",
               "predictive modeling", "automl", "a/b testing"]


def main():
    txt = resume_text()
    parsed = txt is not None
    if not parsed:
        p = Path("data/profile.json")
        if p.exists():
            print("resume .docx absent — keeping committed data/profile.json")
            import json
            d = json.load(open(p))
            d["resume_parsed"] = False
            write_json("data/profile.json", d)
            return
        txt = ""

    lk = [s.lower() for s in linkedin_skills()]
    skills = sorted(set(CORE_SKILLS) | {s for s in lk if s in (
        "python (programming language)", "sql", "r (programming language)",
        "numpy", "machine learning", "forecasting", "microsoft excel",
        "data analysis", "statistics")})
    profile = {
        "generated_at": now_iso(),
        "resume_parsed": parsed,
        "name": "Ahaan Anand",
        "school": "Virginia Tech",
        "majors": ["Computational Modeling & Data Analytics", "Economics"],
        "grad_month": "2028-05",
        "gpa": 3.31,
        "visa_status": "F-1",
        "work_auth_summer_2027": "CPT",
        "resume_text": txt,
        "core_skills": CORE_SKILLS,
        "linkedin_skills": linkedin_skills(),
        "role_family_lexicon": ROLE_FAMILIES,
        "out_of_scope_terms": OUT_OF_SCOPE,
        # Hard-gate phrases: explicit posting language that hard-stops Ahaan
        # regardless of any company sponsorship history (Part 0 #2).
        "eligibility_block_phrases": [
            "must not require sponsorship now or in the future",
            "not require sponsorship", "no sponsorship", "without sponsorship",
            "unable to sponsor", "will not sponsor", "do not sponsor",
            "us citizenship required", "u.s. citizenship required",
            "must be a us citizen", "must be a u.s. citizen",
            "permanent resident", "green card", "security clearance",
            "active clearance", "itar", "export control",
            "unrestricted work authorization",
        ],
        "eligibility_support_phrases": [
            "cpt", "curricular practical training", "opt",
            "student work authorization", "eligible to work",
            "sponsor international", "will sponsor", "f-1", "f1 visa",
        ],
    }
    write_json("data/profile.json", profile)
    print(f"profile built  resume_parsed={parsed}  "
          f"skills={len(skills)}  resume_chars={len(txt)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Campaign 27 V7.1 pipeline. Heavy computation lives in these scripts writing
JSON to disk; the frontend is a thin static viewer over that JSON (Part 0 #6).

Stages run locally with the private inputs (resume .docx, LinkedIn export,
target xlsx/CSV) present. Each stage keeps committed JSON when its private
input is absent, so a CI re-run never clobbers good data with empty output.
"""
import subprocess, sys

STEPS = [
    "build_companies.py",          # Part 1: 163-company source + old/new diff
    "build_profile.py",            # Part 3: resume + LinkedIn -> profile
    "ingest.py",                   # Part 2: real tracker postings, deduped
    "build_network_aggregates.py",  # Part 3: LinkedIn network layer
    "dol_lookup.py",               # Part 3: DOL sponsorship (supporting only)
    "score.py",                    # Part 3: gate + model bake-off + apply
    "calibrate.py",                # Part 3: V4 Bayesian lane calibration
    "portfolio.py",                # Part 0 #5: prior-only portfolio curve
    "build_site.py",               # Part 4/5: assemble sanitized static site
]

if __name__ == "__main__":
    for s in STEPS:
        print("==", s)
        subprocess.check_call([sys.executable, s])

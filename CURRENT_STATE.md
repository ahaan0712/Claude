# Current State Audit — Campaign 27 Foundation Rescue

This repository was audited after PR #4 and before the rescue implementation was finalized. The pre-rescue implementation must not be described as a predictive model.

## Ground truth confirmed

- `score.py` only packaged existing `live_matches`, `review_queue`, and `excluded_postings` into `data/matches.json`; it did not score or rank roles.
- `enrich.py` used a compact keyword rubric for role scope, eligibility, and fit tiers; it was not a meaningful predictive recommendation model.
- `discover.py` generated deterministic fake production postings for target companies such as Capital One, Microsoft, Google, Amazon, and Salesforce.
- `watchlist.py` only added default fields and did not monitor real career pages.
- `import_target_universe.py` scanned multiple workbook worksheets rather than importing only `Target Companies`.
- The repository reported 164 active companies and 204 target programs, but those counts came from broad parsing and were not a genuine V6 reconciliation.
- The authoritative cleaned workbook `Ahaan_2027_Internship_Target_List_Cleaned.xlsx` was not present in this local checkout; the rescue importer uses sanitized derived JSON as a CI-safe fallback.

## CI failure

Failed GitHub Actions logs were not available in the local checkout. Reproduction found the first failure in the dirty post-PR workspace: `python run_pipeline.py` reached `enrich.py`, called `validate_posting`, and failed because `schema.py` required fields that enrichment had not populated: `evidence_source`, `missing_evidence`, `verification_action`, `demonstrated_skills`, `listed_skills`, and `inferred_transferable_skills`. A clean archive of committed `HEAD` passed the existing 7 tests, so the actionable failure was schema/enrichment drift in the repair workspace.

## Source precedence

1. exact live posting text
2. verified résumé/profile
3. cleaned XLSX
4. current official company career pages
5. verified historical evidence
6. V6 reference metadata
7. supplemental tracker data

## Stale or inconsistent generated files observed

- `data/matches.json`
- `data/portfolio.json`
- `data/dol_lookup.json`
- old `data/postings.json` when treated as a primary feed
- pre-rebuild `site/data/*`

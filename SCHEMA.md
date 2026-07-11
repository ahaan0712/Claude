# Campaign 27 V7.1 — Data Contract

The frontend reads only sanitized JSON in `site/data/`.

- **companies.json** — 162 target companies: category, intl_friendly_level, manual_access_tier, career_page_url, typical_opening, deadline_behavior.
- **matches.json** — postings grouped `eligible`/`verify` → fit tier → alphabetical. Every posting: `eligibility_status` (ELIGIBLE|VERIFY|SKIP), `fit_tier` (STRONG/GOOD MATCH|ADJACENT|WEAK MATCH), `calibration_status=PRIOR_ONLY`, `calibrated_probability=null`. No rank field is ever emitted.
- **portfolio.json** — expected-interview curve (`n_applications`, `expected_interviews`, `p10`, `p90`), `calibration_state=PRIOR_ONLY`.
- **model_report.json** — the 9-candidate robustness bake-off, winner, and why others lost.
- **network_aggregates.json** — per-company connection counts (aggregate only).
- **dol_lookup.json** — REAL/NONE/UNKNOWN sponsorship breakdown (supporting evidence only).
- **company_diff.json** — old-vs-new company-list diff.
- **lane_calibration.json** — V4 Bayesian lane posteriors, PRIOR_ONLY until 20 outcomes.
- **coverage.json** / **profile_public.json** — build stats and the PII-free candidate summary.

Eligibility values: ELIGIBLE, VERIFY, SKIP. Fit tiers: STRONG MATCH, GOOD MATCH, ADJACENT, WEAK MATCH. Calibration: PRIOR_ONLY, CALIBRATED.

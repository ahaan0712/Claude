# Campaign 27 Product Spec — Foundation Rescue

Campaign 27 is an XLSX-first Summer 2027 internship monitoring and relative-fit assistant. It is not an interview-probability model and does not publish ranks, point scores, offer probabilities, Monte Carlo output, or Claude priors.

## Source precedence

1. Exact live posting text
2. Verified résumé/profile
3. Cleaned XLSX (`Ahaan_2027_Internship_Target_List_Cleaned.xlsx`, worksheet `Target Companies`)
4. Current official company career pages
5. Verified historical evidence
6. V6 reference metadata for aliases/windows/links/notes only
7. Supplemental tracker data

## Core data products

- `data/target_programs.json` — active programs from the Target Companies worksheet or sanitized CI fallback.
- `data/company_watchlist.json` — active companies and monitoring status, retained even when no live role is open.
- `data/excluded_target_programs.json` — auditable archived rows for user exclusions.
- `data/company_reconciliation_report.json` — source, row, active/archive, duplicate, exclusion, and unresolved-record counts.
- `data/postings_raw.json` — actual target-discovery postings only; must never contain deterministic fixtures.
- `data/supplemental_discoveries.json` — old tracker records marked `SUPPLEMENTAL_TRACKER` only.
- `data/live_matches.json` and `data/review_queue.json` — actual/supplemental postings after eligibility and fit processing.

## Monitoring statuses

Company watchlist entries use `NOT_DUE`, `MONITOR_SOON`, `MONITOR_NOW`, `OPEN_MATCH_FOUND`, `OPEN_BUT_INELIGIBLE`, `OPEN_BUT_OFF_TARGET`, `CHECKED_NO_MATCH`, `RETRIEVAL_BLOCKED`, `RETRIEVAL_FAILED`, or `NEEDS_RESEARCH`. Retrieval failure is never interpreted as no posting.

## Eligibility gate

Eligibility is separate from fit and returns `ELIGIBLE`, `VERIFY`, `SKIP`, or `CLOSED`. Hard skip evidence includes no-sponsorship, citizenship, permanent-resident, security-clearance, ITAR/export-control, incompatible graduation, graduate-only/MBA-only, excluded role, and excluded industry language. Missing CPT/sponsorship/Summer 2027/undergraduate/graduation/full-description/citizenship evidence produces `VERIFY`.

## Fit model

The current fit model is a deterministic cold-start model using role relevance, skill overlap, résumé-evidence traceability, screening compatibility, domain alignment, posting quality, and capped lexical overlap. Public output is limited to `STRONG MATCH`, `GOOD MATCH`, `ADJACENT`, or `WEAK MATCH` plus application-priority labels. Weights are documented in `config_model_weights.json`.

## Outcomes and calibration

Application tracking supports applied, online assessment, recruiter screen, interview, final round, rejected, offer, and withdrawn states. Calibration remains `PRIOR_ONLY` and `calibrated_probability` remains `null` until enough user outcomes exist in a lane.

## Frontend

The static site provides Dashboard, Target Programs, Company Watchlist, Live Matches, Review Queue, Supplemental Discoveries, Saved, Applications, Network, and Coverage views. It works when live matches are zero and stores application tracking only in browser `localStorage` with JSON/CSV export.

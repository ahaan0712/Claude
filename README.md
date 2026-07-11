# Ahaan Anand Summer 2027 Internship Recommendation Engine — Phase 1

This repository now serves a static GitHub Pages-compatible personalized recommendation feed for Ahaan Anand's Summer 2027 undergraduate analytics internship search.

## What Phase 1 does

`score.py` reads `data/postings.json`, `profile_verified_from_resume.json`, and optional `data/dol_lookup.json`, then writes `data/matches.json` using the required normalized posting schema. The engine is deliberately cold-start and explainable:

1. deterministic hard gates for Summer 2027 undergraduate scope, graduation-window compatibility, work authorization, role relevance, and hard-excluded industries;
2. strict exclusion of quant, trading, SWE, hardware, IT support, cybersecurity, incompatible authorization, clearance, ITAR/export-control, and excluded-industry roles;
3. role-family confidence for Data Analyst, Data Analytics, Data Science, Business Intelligence, and Business Analytics, with limited adjacent analytics families;
4. verified skill and résumé evidence matching from Ahaan's résumé/profile;
5. BM25 lexical similarity as one normalized signal, not the whole system;
6. visible sponsorship uncertainty: posting-level language controls, company history is supporting evidence only;
7. freshness and application urgency labels;
8. final application priority labels instead of interview probabilities.

## Cold-start scoring configuration

The temporary Phase 1 weights live in `PHASE1_WEIGHTS` inside `score.py`:

- role fit: 0.30
- verified skill match: 0.22
- BM25 lexical similarity: 0.16
- response-outlook signal: 0.14
- sponsorship support: 0.07
- freshness: 0.07
- industry preference: 0.04

Eligibility and Summer 2027 scope are hard gates before ranking. These weights are not a validated probability model and should be recalibrated only after Ahaan has real application outcomes.

## Static frontend

`index.html` renders `data/matches.json` as a personalized internship feed. It supports filters for Apply Now, Eligible, Verify First, the five primary role families, Saved, and Applied. Application tracking is stored in browser `localStorage` using these statuses: saved, dismissed, applied, online_assessment, recruiter_screen, interview, final_round, rejected, offer, withdrawn.

## Data limitations

The current source feed contains limited posting descriptions, so many entries correctly become `VERIFY` or `SKIP`. Company-level H-1B/LCA history never proves CPT acceptance for a specific internship. The next data-quality step is to enrich postings with full descriptions and application-question evidence from source pages.

## Development

Run scoring:

```bash
python score.py --as-of 2026-07-11
```

Run tests:

```bash
python -m pytest -q
```

## Phase 2 plan

- Add a human review file for recommendation labels and verification decisions.
- Export application outcomes from localStorage into `data/outcomes.csv`.
- Add posting-description ingestion from job pages where permitted.
- Calibrate response-outlook tiers after enough real outcomes exist.
- Consider gradient-boosted learning-to-rank, Bayesian calibration, and portfolio optimization only after validated labels are available.

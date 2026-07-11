# Campaign 27 — Summer 2027 Internship Matcher (V7.1)

A posting-level internship matcher for Ahaan Anand (F-1 international student,
Virginia Tech CMDA + Economics, May 2028, targeting analytics / BI / data
science / economic-consulting internships for Summer 2027).

The unit of prediction is **one exact posting**, never a company. Eligibility
is a **hard gate**, fit is a **grouped tier** (never a point rank), and **no
interview probability is published** until it is calibrated against real logged
outcomes. The headline is a portfolio curve — *apply to top N postings →
expected interviews* — with honest, wide uncertainty bands.

## Pipeline (`python run_pipeline.py`)

Heavy computation lives in scripts writing JSON to `data/`; the frontend is a
thin static viewer that recomputes nothing.

| Stage | Script | Output |
|-------|--------|--------|
| 1. Companies | `build_companies.py` | `companies.json`, `company_diff.json` — the 162-company universe from `authoritative_target_companies.csv`, plus the old-vs-new diff |
| 2. Profile | `build_profile.py` | `profile.json` — resume (.docx) + LinkedIn skills, PII-stripped |
| 3. Postings | `ingest.py` | `postings_raw.json` — real Summer-2027 tracker postings, source-tagged, deduped by company+role+month |
| 4. Network | `build_network_aggregates.py` | `network_aggregates.json` — company-level LinkedIn connection signal (aggregate only) |
| 5. DOL | `dol_lookup.py` | `dol_lookup.json` — sponsorship history (supporting evidence only; UNKNOWN on failure, never a fabricated NONE) |
| 6. Model | `score.py` + `model.py` | `matches.json`, `model_report.json` — eligibility gate + fit-model bake-off + grouped matches |
| 7. Calibrate | `calibrate.py` | `lane_calibration.json` — V4 Bayesian posterior (PRIOR_ONLY until 20 outcomes/lane) |
| 8. Portfolio | `portfolio.py` | `portfolio.json` — the headline expected-interview curve |
| 9. Site | `build_site.py` | `site/` — sanitized static viewer |

## The fit model (chosen for robustness, not accuracy)

Because there are **zero logged outcomes**, real-world accuracy is unmeasurable.
`score.py` runs a bake-off of 3 fit scorers (`tfidf_resume`, `skill_overlap`,
`role_family`) × 3 combiners (`additive`, `multiplicative`, `lexicographic`)
and auto-selects the candidate that minimises a robustness cost:

- **tier-flip instability** under bootstrap input perturbation,
- **Pareto violations** (ranking a dominated posting above its dominator),
- **auxiliary-feature dominance** (a timing/network/access feature silently
  controlling the order — the V6 "Claude prior" failure mode), and
- **poor discrimination** (collapsing every posting into one tier).

The current winner and the full scoreboard live in `data/model_report.json`.

## Private inputs

Resume `.docx`, the LinkedIn export (`data/linkedin_export/`), and the target
workbook are git-ignored. Each stage falls back to committed JSON when its
private input is absent, so CI/Pages re-runs never clobber good data.

## Develop

```bash
python run_pipeline.py     # full pipeline -> data/ + site/
python -m pytest -q        # invariant tests (hard gate, no ranks/probabilities, PII-safe)
```

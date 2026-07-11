# Campaign 27 V7.1 — Audit / Rebuild / Ship Report

Session date: 2026-07-11. Branch: `claude/campaign-27-v7-audit-ofzs28`.

## TL;DR
The pipeline was an honest but non-functional skeleton (a passthrough `score.py`,
an empty portfolio curve, `dol_lookup` hardwired to UNKNOWN, `ingest` that never
fetched trackers, and a resume/network layer that was read by nothing). It is now
a working, honest matcher: 162-company source, 202 real Summer-2027 postings, a
resume-driven fit model chosen by a robustness bake-off, a real LinkedIn network
layer, V4-wired calibration, and a portfolio-curve frontend. All Part 0
non-negotiables hold and are locked by tests. **The only thing not done for me is
the live Pages URL — it is blocked by a repo setting I can't change (see §10).**

## 1. Which XLSX, and why
The task said "a new xlsx with 163 companies." The most recent upload in git is
`authoritative_target_companies.csv` (commit 50f2fbb) — a machine-readable export
of the **"Target Companies" sheet of `Ahaan 2027 Internship Target List.xlsx`**
(163 rows incl. header = **162 companies**; it carries `_source_excel_row` /
`_source_record_id` provenance columns). I used the CSV as the canonical source
because it is the latest committed upload, is byte-identical in schema to that
xlsx sheet, and is CI-reproducible (the xlsx is git-ignored as a private file). I
recovered the deleted xlsx/resume/LinkedIn files from git history (commit e163fda
had deleted them) to run the pipeline locally. The `Ahaan_2027_Evidence_Driven_
Model_V6.xlsx` is the **old, broken company-ranking model V7 replaced** — I did
NOT use it as a source.

## 2. What changed between the 163-list and the old list
Diffed against a frozen snapshot of the previous committed `company_watchlist.json`
(164 rows):
- **+12 genuinely new companies**, almost all finance: BNP Paribas, Freddie Mac,
  J.P. Morgan, McKinsey & Company, Morgan Stanley, Nomura, RBC Capital Markets,
  SIG (Susquehanna), State Street, Two Sigma, UBS, Wells Fargo.
- **-14 "dropped"** — these were **not companies**: the old parse had ingested
  strategy-note rows as fake companies ("GPA strategy", "Referral script",
  "ELIGIBILITY KILL-PHRASE (memorize)", "YOUR PORTFOLIO NUMBERS",
  "v3.1 - INTERVIEW-FIRST + SORTED", …). The new clean load removes that pollution.
- **150 retained.** Result: 162 real companies vs a previously-polluted 164.
- Full detail in `data/company_diff.json`.

**Judgment call:** the source's "Your Realistic Odds (per application)" column
contained baked-in `P(INTERVIEW)/P(offer)` numbers. I **dropped** those — they are
exactly the unvalidated V6-style probabilities the design forbids publishing. I
kept only the bracketed tier tag ([STRONG TARGET]/[TARGET]/[STRETCH]/[REACH]/
[LONG SHOT]) as a company-level "access" signal that never sets the eligibility
gate and is never a silent scoring tiebreaker.

## 3. Where postings data now comes from + coverage
`ingest.py` pulls **real** Summer-2027 postings from public GitHub trackers,
tags each with its source, and dedups by company+role-family+month:
- **vanshb03/Summer2027-Internships** — 148 internship listings (structured JSON).
- **sndsh404/summer-2027-internships** — 69 (markdown table parsed).
- **217 raw → 202 deduped** postings across **112 companies**.
- **SimplifyJobs and Pitt CSC have NOT published a Summer-2027 repo yet** (their
  2027 URLs 404; only 2026 exists). `ingest.py` records source successes/failures
  and raises rather than writing an empty file if all sources fail — a failed
  fetch is never presented as "no postings."
- **Career pages:** I confirmed 155/162 companies carry a career URL in the source
  and they're surfaced in the UI, but I did **not** wire live career-page scraping:
  the target companies are Workday/Greenhouse/Oracle JS-rendered boards that don't
  yield JobPosting JSON-LD from a plain GET, so a naive fetcher would mostly
  produce "no postings found" — the exact silent-failure the audit warns against.
  This is logged honestly rather than faked. (See §11 for the follow-up option.)

## 4. Model-testing harness — what it found and which candidate won
`score.py` + `model.py` run a genuine bake-off: **3 fit scorers**
(`tfidf_resume`, `skill_overlap`, `role_family`) × **3 combiners** (`additive`,
`multiplicative`, `lexicographic`) = 9 candidates, each scored on robustness
(NOT accuracy — there are zero logged outcomes, so accuracy is unmeasurable):
- **bootstrap tier-flip instability** under small input perturbation,
- **Pareto consistency** (never rank a dominated posting above its dominator),
- **auxiliary-feature dominance** (a timing/network/access feature controlling the
  order — the V6 "Claude prior" failure; fit is *allowed* to dominate by design),
- **discrimination** (a model that collapses everything into one tier is stable
  but useless — penalised).

**Winner: `role_family × multiplicative`** (cost 1.12): flip-rate 12%, **0 Pareto
violations**, aux-dominance 0.58 (below the 0.60 penalty line), discrimination 0.41.
An early bug in my first cost function rewarded a degenerate `tfidf × lexicographic`
that put all 17 postings in one tier — I fixed it by adding the discrimination term
and by only penalising *auxiliary* dominance (fit dominating is correct). The
degenerate tfidf candidates now correctly rank last. Full scoreboard +
"why each lost" in `data/model_report.json` and on the site's Model tab.
**"Best" here means most robust and least noisy, not most historically accurate —
that claim is unavailable until Ahaan logs outcomes.**

Resume and dates are genuinely wired: `build_profile.py` parses the `.docx` (3.8k
chars) + 53 LinkedIn skills into `data/profile.json` (previously the resume JSON
was read by nothing); the timing feature computes days-since-posted from real
parsed `date_posted`, with an explicit neutral 0.5 when a date is genuinely absent
(not a placeholder-as-fact).

## 5. Eligibility gate + honesty audit
- The gate is a **hard stop**: explicit citizenship/clearance/no-sponsorship
  language (or the tracker "U.S. Citizenship is Required" field) → SKIP, before any
  scoring, regardless of DOL history. Verified no SKIP posting reaches the published
  output (14 land in the excluded lane with their evidence).
- **calibrate.py was silently NOT using the V4 math** despite the legacy docstring
  claiming it did — it had been replaced with a trivial counter. I re-wired it to
  genuinely import `ROLE_PRIORS`/`logit`/`logistic`/`posterior_delta_grid` from
  `legacy/ahaan_model_v4_update.py`. It stays PRIOR_ONLY and publishes no
  probability until a lane has 20 logged outcomes.
- Current result: eligible **0**, verify **17**, hard-blocked **14**. Zero
  "eligible" is honest — titles-only tracker data can't confirm work-auth, so
  in-scope roles are correctly VERIFY, not a fabricated ELIGIBLE.

## 6. DOL REAL/NONE/UNKNOWN breakdown
`data/dol_lookup.json`: **REAL 0 · NONE 0 · UNKNOWN 162.** The official DOL
disclosure source (flag.dol.gov) and every H-1B mirror I tried are unreachable
from this environment (000/404). `dol_lookup.py` genuinely attempts the fetch and,
on failure, marks every company UNKNOWN with the error surfaced — **never a
fabricated NONE or REAL.** DOL is supporting evidence only; the real work-auth
signal is the posting-level `sponsorship` field in the eligibility gate.

## 7. What the LinkedIn layer changed
Previously `network_aggregates.json` was **all zeros** (it read `Connections.csv`
from the repo root, where it's git-ignored/absent). `build_network_aggregates.py`
now reads the restored export (`data/linkedin_export/`): **518 connections parsed**,
**10 target companies with a warm path**, e.g. Deloitte (6 connections, 2 in
analytics → STRONG), EY (4), IBM/PwC/Amex (analytics contacts), plus Amazon,
Google, Microsoft, McKinsey, PepsiCo. Aggregate counts only — no names/emails/URLs
are emitted or published. Network is a bounded tie-breaker, never a dominant weight.

## 8. What the code-reviewer flagged and how I resolved it
A reviewer subagent audited the model + frontend and returned per-file verdicts
(all SOLID) plus **2 real problems**, both fixed:
1. **`fit_score_internal` was published in `matches.json`** — a per-posting numeric
   score anyone could sort by to reconstruct the within-tier leaderboard the spec
   forbids. **Fixed:** the raw score stays in-memory for tier assignment only and is
   no longer emitted; added a test asserting no score field is published.
2. **Eligibility used bare-substring matching** — short tokens ("opt", "cpt",
   "itar") misfired ("optimize"→false ELIGIBLE, "military"→false SKIP). Dormant now
   (titles-only) but dangerous once descriptions arrive. **Fixed:** word-boundary
   matching in `model.py`, with regression tests.
All 15 invariant tests pass; the full pipeline runs clean end-to-end.

## 9. Cleanup
Removed dead code the audit found: `discover.py`, `enrich.py`, `watchlist.py`,
`import_target_universe.py`, `build_reports.py`, and the `providers/` package (six
byte-identical duplicate modules, imported by nothing). Removed ~15 stale data
files from the retired pipeline. Rewrote the test suite around the new invariants.
CI now installs pytest and runs the new pipeline; docs (README/DESIGN/SCHEMA/
PRODUCT_SPEC) updated to V7.1.

## 10. Live Pages URL — the one thing needing you
CI proves the build is healthy: the **build job is green** (pip install →
`run_pipeline.py` → 15 tests pass → Pages artifact uploaded). The **deploy job
fails instantly with no runner** — GitHub rejected it because the **`github-pages`
environment only permits deployments from the default branch**
(`claude/campaign-27-v7-matcher-ofaf2m`), and I'm working on the audit branch and
am not permitted to push to or merge into the default branch. I updated the
workflow to allow the audit branch, but the environment branch-policy override
lives in repo Settings, which I can't change via API.

**To get the live link (either one, ~30 seconds):**
- **Easiest:** merge `claude/campaign-27-v7-audit-ofzs28` into the default branch —
  the existing `deploy-pages.yml` then deploys automatically; **or**
- Settings → Pages → ensure Source = "GitHub Actions", and (if needed) Settings →
  Environments → `github-pages` → allow the `claude/campaign-27-v7-audit-ofzs28`
  branch, then re-run the "Deploy GitHub Pages" workflow.

Expected URL: **https://ahaan0712.github.io/Claude/**

I verified the exact committed artifact renders correctly (Chromium, desktop +
390px mobile): portfolio curve with p10–p90 band and PRIOR_ONLY badge, matches
grouped by eligibility → fit tier with no point rank, model bake-off, 162-company
table, network cards. No console errors beyond a favicon 404.

## 11. Open follow-ups (optional, not blockers)
- Career-page ingestion for the STRONG tier would need per-ATS adapters
  (Workday/Greenhouse/Oracle) — real work, deferred rather than faked.
- Everything unlocks further once you start logging application outcomes in
  `data/outcomes.csv`: lanes flip PRIOR_ONLY → CALIBRATED at 20 outcomes and the
  portfolio curve becomes a real forecast instead of a prior.

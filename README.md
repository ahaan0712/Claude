# Campaign 27 V7 — Posting-Level Internship Matcher

Ahaan Anand · F-1 international student · Virginia Tech, B.S. Computational
Modeling & Data Analytics + B.S. Economics · May 2028 · targeting Summer 2027
analytics / economic-consulting internships.

## Why V7 exists

V6 (`Ahaan_2027_Evidence_Driven_Model_V6.xlsx`) ranked 157 **companies** with a
7-feature Monte Carlo simulation. Its own diagnostics said not to trust the
ranking:

- Weight-sampling contributed ~12 ranks of spread; feature-value noise
  contributed ~49. The weights barely mattered — the noisy feature guesses did.
- The "Claude prior" was the only continuous feature in the model and silently
  drove ordering: removing it moved ranks by a median of 14 and up to 38.
- CPT score defaulted to one of two values for 138 of 157 companies — i.e. for
  88% of the board, "evidence" was really a coin flip.
- Only 40 of 157 companies had any real supporting evidence at all.
- The full 7-feature model correlated 0.83 with a 3-rule heuristic — nearly all
  of the machinery was reproducing what three rules already captured.

A precise-looking rank on top of that much noise is false precision. **V7 stops
ranking companies.** It scores individual postings, gates on eligibility before
anything else, and refuses to output a probability until there's enough of
Ahaan's own outcome data to justify one.

## Pipeline

```
ingest.py     →  data/postings.json
dol_lookup.py →  data/dol_lookup.json      (needs data/postings.json)
score.py      →  data/matches.json         (needs data/postings.json, data/profile.json, data/dol_lookup.json)
calibrate.py  →  data/lane_calibration.json  (needs data/outcomes.csv)
portfolio.py  →  data/portfolio.json       (needs data/matches.json, data/lane_calibration.json)
app.html      →  reads data/matches.json + data/portfolio.json
```

Every script is stdlib-only Python 3.9+ (no pip installs required) and writes
its full output to JSON on disk. Nothing above prints a large data dump to the
terminal — run the scripts, then look at the JSON or the viewer.

### 1. `ingest.py` — pull postings

```
python3 ingest.py
```

Fetches the Summer 2027 posting tables from two public GitHub trackers
([`vanshb03/Summer2027-Internships`](https://github.com/vanshb03/Summer2027-Internships),
[`sndsh404/summer-2027-internships`](https://github.com/sndsh404/summer-2027-internships)),
parses their markdown tables (including the 🛂 no-sponsorship / 🇺🇸 US-citizens-only
/ 🔒 closed badges both trackers use), and merges in any rows pasted from
Simplify into `data/simplify_paste.txt` (Simplify has no public API — copy rows
out of its table, tab- or pipe-separated, one per line). Output is cached to
`data/postings.json`; a failed fetch for one source doesn't wipe the cache from
a prior run. Use `--no-fetch` to rebuild only from the paste-in file and the
existing cache.

### 2. `dol_lookup.py` — real H-1B/LCA filing counts per company

```
python3 dol_lookup.py
```

Pulls real Labor Condition Application (LCA) filing counts, per company on
the ingested posting board, from DOL OFLC's public LCA Disclosure Data files
(no key required) with [`h1bdata.info`](https://h1bdata.info) as a
per-company fallback for anything the DOL bulk files don't turn up. Company
names are matched via `companies.py`'s shared alias/normalization table (the
same one `score.py` uses), so "Capital One" on a posting matches whatever
legal-entity form DOL filed under.

For each company, `data/dol_lookup.json` records `fiscal_year_filings` for
the last 3 federal fiscal years, `total_filings_3yr`, a `trend`
(rising/flat/falling), and a `sponsorship_evidence` status that is **only**
one of:

- `REAL` — a source was reached and returned ≥1 filing.
- `NONE` — a source was reached and returned zero filings.
- `UNKNOWN` — neither DOL nor h1bdata.info could be reached for this company.
  **Never collapsed into `NONE`** — a blocked/failed fetch is not evidence of
  anything, and this project's whole premise is not fabricating certainty
  that isn't there.

**Network note:** this script needs real outbound internet to `dol.gov` and
`h1bdata.info`. Sandboxed environments that only allow GitHub traffic (like
the one this repo was originally built in) will report every company as
`UNKNOWN` — that's the honest result of a blocked fetch, not a bug. The
`.github/workflows/dol_lookup.yml` Action runs it on a GitHub-hosted runner,
which has unrestricted outbound internet, and commits the refreshed
`data/dol_lookup.json` (plus a re-run of `score.py`/`calibrate.py`/
`portfolio.py`) back to this branch. Trigger it from the Actions tab, or run
the script locally on a machine with normal internet access.

There's no `data/company_board.xlsx` in this repo — V7's board *is* whatever
`ingest.py` pulled into `data/postings.json` (currently ~110 distinct
companies), not the old V6 spreadsheet's fixed 157. For a fixed sanity-check
set, `STRONG_TARGET_COMPANIES` in `dol_lookup.py` names 13 large, well-known
employers already on that board (Capital One, JPMorganChase, Citi, Bank of
America, BlackRock, BNP Paribas, DTCC, Fiserv, Salesforce, Microsoft, Amazon,
Databricks, Twilio) that a correctly-working lookup should be able to find
real LCA history for. That list is only used to print a coverage check at the
end of a run — it is never surfaced as a company ranking anywhere.

### 3. `score.py` — score per posting, not per company

```
python3 score.py
```

For each posting:

1. **Eligibility gate** (runs first, hard stop): tracker badges and posting
   text are scanned for explicit CPT/OPT/sponsorship/citizenship blocks. A hit
   → `INELIGIBLE`, full stop, no fit score changes that — company-level DOL
   filing history never overrides an explicit posting-language block, per the
   V6 lesson that exact wording controls. A closed-tracker badge → `CLOSED`.
   Ambiguous language (mentions "sponsorship"/"CPT"/"visa" without a clear
   block) → `VERIFY`. For `VERIFY` and the default `ELIGIBLE` state, the
   posting's `sponsorship_evidence` card (from `dol_lookup.py`) is attached:
   real filing counts + trend when evidence is `REAL`, an explicit "no filing
   history found — rely on exact posting language" when `NONE`, and a "not
   yet checked" note when `UNKNOWN`/lookup hasn't been run — replacing what
   would otherwise be a guessed default.
2. **Fit**: dependency-free TF-IDF cosine similarity between Ahaan's résumé
   text (`data/profile.json`) and the posting text, multiplied by a
   role-family match multiplier (keyword-based lane assignment across the 10
   analytics/consulting lanes) and an off-target penalty for SWE/hardware/
   quant-trading postings that leak into the analytics-focused trackers.
3. **Timing**: a decay multiplier — freshness under 7 days is the one edge V6
   actually documented — with a ~21-day half-life afterward, floored so an
   older-but-relevant posting is discounted, not zeroed.
4. **Preference**: a multiplier from Ahaan's stated preferred (modern tech,
   fintech/payments, data platforms, marketplaces, media, consulting) and
   deprioritized (insurance, hospitality, manufacturing, quant trading,
   unrelated SWE/hardware) industries.

Output (`data/matches.json`) is a **fit score (0–100) and an eligibility
state** per posting, bucketed into a coarse `fit_tier` (Strong / Good /
Exploratory). There is no probability anywhere in this file.

### 3. `calibrate.py` — wraps the existing V4 Bayesian updater

```
python3 calibrate.py
```

The original V4 lane-level Bayesian logit updater
(`legacy/ahaan_model_v4_update.py`, kept verbatim) is imported, not
reimplemented — `calibrate.py` only replaces the I/O layer, reading
`data/outcomes.csv` (one row per posting Ahaan actually applied to:
`posting_id,company,role,role_family,applied,interviewed,date`) instead of the
workbook's exported sheets.

**Hard rule: a role-family lane only gets a `published_probability` once it
has ≥20 logged outcomes.** Below that, the lane is labeled `PRIOR-ONLY` in
`data/lane_calibration.json` and `published_probability` is `null` — a
separate `reference_prior` field carries V4's original unvalidated prior band,
explicitly captioned as not a probability, so it stays available for
transparency without being presented as calibrated. As of this repo's initial
commit, `data/outcomes.csv` has zero logged rows, so **all 10 lanes are
PRIOR-ONLY** — that's the honest starting state, not a bug. Log real
outcomes as Ahaan applies and re-run this script to move lanes toward
DATA-BACKED.

### 4. `portfolio.py` — the headline, not a ranking

```
python3 portfolio.py
```

Computes **"apply to top N eligible postings → expected interviews"** as a
Monte Carlo curve with 10th/90th-percentile uncertainty bands (lane-level
probability draws are shared across every posting in that lane per draw, so
correlated lane uncertainty isn't washed out by treating postings as
independent). "Top N" here is an internal ordering by fit score used only to
decide which postings accumulate into the curve as N grows — it is not
exposed as a per-posting rank anywhere.

Postings in `DATA-BACKED` lanes feed a **calibrated curve**. Postings in
`PRIOR-ONLY` lanes are kept in a separate **illustrative curve** built from
V4's unvalidated priors — they are never blended into the calibrated headline
number. `data/portfolio.json` carries a `basis` field
(`NO_CALIBRATED_LANES` / `PARTIAL` / `FULLY_CALIBRATED`) so the UI (and
anyone reading the JSON) always knows which curve, if either, is trustworthy.

### 5. `app.html` — thin viewer

```
python3 -m http.server 8000
# open http://localhost:8000/app.html
```

(Must be served over HTTP — `fetch()` of local JSON is blocked from a
`file://` URL.) Reads `data/matches.json` and `data/portfolio.json` directly;
no build step, no framework, no external requests. Postings are grouped by
**eligibility, then fit tier** — never a single point rank. Each card shows
fit score, days since posted, role family, and the eligibility reason. The
portfolio section shows both curves from `portfolio.py` with their basis
clearly labeled.

## Re-running the full pipeline

```
python3 ingest.py
python3 dol_lookup.py
python3 score.py
python3 calibrate.py
python3 portfolio.py
```

## GitHub Pages

`app.html` is deployed by `.github/workflows/pages.yml` on every push to this
branch that touches `app.html` or `data/**` (or manually via
workflow_dispatch). It copies `app.html` to `index.html` at the site root
along with `data/`, so the whole tool is one bookmarkable URL with no
`/app.html` suffix needed:

```
https://ahaan0712.github.io/Claude/
```

## GitHub Actions

- **`dol_lookup.yml`** — runs `dol_lookup.py` → `score.py` → `calibrate.py` →
  `portfolio.py` on a GitHub-hosted runner (real outbound internet) and
  commits any data changes back to this branch. Manual trigger or monthly
  cron.
- **`pages.yml`** — builds and deploys `app.html` + `data/` to GitHub Pages,
  described above.

## Logging outcomes

Append rows to `data/outcomes.csv` as Ahaan applies and hears back:

```
posting_id,company,role,role_family,applied,interviewed,date
vanshb03/summer2027-internships:capital one:data analyst intern:...,Capital One,Data Analyst Intern,Data Analytics,1,0,2026-07-15
```

`role_family` must match one of the 10 lanes in `data/profile.json`. Once a
lane crosses 20 rows, `calibrate.py` will publish a probability for it and
`portfolio.py` will move its postings into the calibrated curve.

## Repository layout

```
data/
  profile.json          Ahaan's profile/résumé signal (extracted from V6 workbook), role-family keyword taxonomy
  postings.json          raw ingested postings (ingest.py output)
  simplify_paste.txt      paste-in target for Simplify rows
  dol_lookup.json          per-company LCA filing counts / trend / sponsorship_evidence (dol_lookup.py output)
  matches.json            scored postings: fit + eligibility + sponsorship evidence (score.py output)
  outcomes.csv             Ahaan's logged application outcomes (append-only, starts empty)
  lane_calibration.json    per-lane Bayesian posterior / PRIOR-ONLY status (calibrate.py output)
  portfolio.json           expected-interviews curves (portfolio.py output)
legacy/
  ahaan_model_v4_update.py  original V4 Bayesian updater, kept verbatim; calibrate.py imports from it
.github/workflows/
  dol_lookup.yml            runs the DOL/h1bdata pull + re-score on a GitHub-hosted runner, commits results
  pages.yml                 deploys app.html + data/ to GitHub Pages
companies.py               shared company-name alias/normalization table (dol_lookup.py + score.py)
ingest.py / dol_lookup.py / score.py / calibrate.py / portfolio.py
app.html
```

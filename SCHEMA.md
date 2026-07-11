# Campaign 27 Canonical Schema

Canonical posting records use `schema.py::CANONICAL_POSTING_FIELDS` and are validated before public JSON generation.

Eligibility values: `ELIGIBLE`, `VERIFY`, `SKIP`, `CLOSED`.
Fit tiers: `STRONG MATCH`, `GOOD MATCH`, `ADJACENT`, `WEAK MATCH`.
Retrieval values: `FULL`, `PARTIAL`, `TITLE_ONLY`, `BLOCKED`, `FAILED`, `CLOSED`.
Calibration values: `PRIOR_ONLY`, `CALIBRATED`, `INSUFFICIENT_DATA`.

Primary public files are separated by purpose: target programs, company watchlist, raw/enriched postings, live matches, review queue, excluded postings, closed postings, supplemental discoveries, coverage, network aggregates, and model/feature audits.

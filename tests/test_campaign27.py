"""Campaign 27 V7.1 invariant tests.

These lock the Part 0 non-negotiables: hard eligibility gate, no point ranks,
no published probability, PRIOR_ONLY until calibration, V4 calibration linkage,
robust model selection, and a PII-safe published site.
"""
import json, subprocess, sys, os, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import model as M
from companies import normalize_name, match_company
from calibrate import LANE_TO_V4
from ahaan_model_v4_update import ROLE_PRIORS, posterior_delta_grid


def profile():
    return json.load(open("data/profile.json"))


# ---- eligibility hard gate -------------------------------------------------
def test_gate_blocks_citizenship():
    p = profile()
    post = {"title": "Data Analyst Intern",
            "full_description": "Must be a US citizen. Security clearance required."}
    assert M.eligibility(post, p)[0] == "SKIP"


def test_gate_blocks_no_sponsorship_tracker_field():
    p = profile()
    post = {"title": "Data Analyst Intern",
            "sponsorship_hint": "U.S. Citizenship is Required"}
    assert M.eligibility(post, p)[0] == "SKIP"


def test_gate_verify_when_silent():
    p = profile()
    post = {"title": "Business Intelligence Intern", "sponsorship_hint": "Other"}
    assert M.eligibility(post, p)[0] in ("VERIFY", "ELIGIBLE")


def test_gate_word_boundary_no_false_positives():
    """Short gate tokens must not misfire on substrings: 'optimize'/'adopt'
    must NOT read as work-auth support, 'military' must NOT read as ITAR."""
    p = profile()
    assert M.eligibility(
        {"full_description": "We optimize dashboards and adopt options"},
        p)[0] == "VERIFY"
    assert M.eligibility({"title": "Military Systems Data Analyst"}, p)[0] \
        != "SKIP"
    # a real CPT mention still supports
    assert M.eligibility(
        {"full_description": "CPT and OPT students are welcome"}, p)[0] \
        == "ELIGIBLE"


def test_gate_does_not_leak_skip_to_scored_output():
    m = json.load(open("data/matches.json"))
    for bucket in ("eligible", "verify"):
        for tiers in m[bucket].values():
            for arr in tiers.values():
                for it in arr:
                    assert it["eligibility_status"] != "SKIP"


# ---- role classification ---------------------------------------------------
def test_classify_scope():
    p = profile()
    assert M.classify("Data Analyst Intern", p) == "DATA_ANALYTICS"
    assert M.classify("Software Engineer Intern", p) == "OUT_OF_SCOPE"


# ---- no ranks / no probability ---------------------------------------------
def test_no_probability_published():
    m = json.load(open("data/matches.json"))
    blob = json.dumps(m)
    for bucket in ("eligible", "verify"):
        for tiers in m[bucket].values():
            for arr in tiers.values():
                for it in arr:
                    assert it["calibrated_probability"] is None
                    assert it["calibration_status"] == "PRIOR_ONLY"
    assert not re.search(r"#\d+\b", blob)
    assert "/100" not in blob
    # no raw per-posting fit score may be published (would be a hidden
    # within-tier leaderboard, violating "no point ranks")
    for bucket in ("eligible", "verify"):
        for tiers in m[bucket].values():
            for arr in tiers.values():
                for it in arr:
                    assert "fit_score_internal" not in it
                    assert not any(k for k in it if "score" in k.lower())


def test_portfolio_prior_only():
    pf = json.load(open("data/portfolio.json"))
    assert pf["calibration_state"] == "PRIOR_ONLY"
    assert "PRIOR_ONLY" in pf["disclaimer"]


# ---- calibration wired to V4 ----------------------------------------------
def test_calibrate_uses_v4_math():
    assert "Data Analytics" in ROLE_PRIORS
    assert posterior_delta_grid([]) == (0.0, 1.0)
    cal = json.load(open("data/lane_calibration.json"))
    assert all(l["calibration_status"] == "PRIOR_ONLY" for l in cal["lanes"])
    assert all(l["calibrated_probability"] is None for l in cal["lanes"])
    assert set(l["v4_prior_lane"] for l in cal["lanes"]) <= set(ROLE_PRIORS)


# ---- model selection robustness -------------------------------------------
def test_winner_has_no_pareto_violations():
    mr = json.load(open("data/model_report.json"))
    met = mr["winner"]["metrics"]
    assert met["pareto_violation_rate"] == 0.0
    assert met["discrimination"] > 0.1          # must actually discriminate
    assert met["aux_feature_dominance"] <= 0.85  # aux must not dominate


def test_dedup_reduces_postings():
    raw = json.load(open("data/postings_raw.json"))
    assert raw["deduped_count"] <= raw["raw_count"]


# ---- company universe ------------------------------------------------------
def test_company_count_162():
    c = json.load(open("data/companies.json"))
    assert c["count"] == 162
    diff = json.load(open("data/company_diff.json"))
    assert diff["summary"]["added"] > 0


# ---- DOL honesty -----------------------------------------------------------
def test_dol_never_fake_none_on_failure():
    d = json.load(open("data/dol_lookup.json"))
    if not d["source_reachable"]:
        assert d["summary"]["NONE"] == 0
        assert d["summary"]["UNKNOWN"] > 0


# ---- normalization ---------------------------------------------------------
def test_normalize_and_match():
    assert normalize_name("Capital One, N.A.") == "capital one"
    assert match_company("Google", "Alphabet")["match"] is True
    assert match_company("", "x")["match"] is False


# ---- published site is PII-safe -------------------------------------------
def test_site_has_no_pii():
    subprocess.check_call([sys.executable, "build_site.py"])
    site = Path("site")
    for p in site.rglob("*.json"):
        t = p.read_text("utf-8")
        assert "253-486-0794" not in t and "253 486 0794" not in t
        assert "ahaan07@vt.edu" not in t
    assert not any(p.suffix == ".csv" for p in site.rglob("*"))
    assert not (site / "data" / "profile.json").exists()

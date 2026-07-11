#!/usr/bin/env python3
"""Part 3 — fit model, candidate bake-off, and robustness harness.

This module holds the modelling primitives shared by the scorer and the
selection harness:

  * the eligibility HARD GATE (Part 0 #2),
  * three candidate fit scorers (TF-IDF, skill-overlap, role-family),
  * three candidate combiners (additive / multiplicative / lexicographic),
  * robustness metrics (bootstrap tier stability, Pareto consistency,
    single-feature dominance).

There are ZERO logged outcomes, so nothing here is validated for real-world
accuracy. Selection optimises for ROBUSTNESS (stable, monotonic, no single
feature silently controlling the order — the V6 "Claude prior" failure), not
accuracy. score.py imports the winning (fit, combiner) pair and applies it.

Pure stdlib: TF-IDF, cosine, and Kendall tau are implemented by hand so the
project keeps its "no third-party runtime deps" contract.
"""
from __future__ import annotations
import math, re, random
from collections import Counter

# ------------------------------------------------------------------ tokens ---
_STOP = set("a an the of and or to for in on with at by intern internship "
            "summer 2027 2026 co op program us usa remote hybrid new".split())


def toks(text):
    return [t for t in re.sub(r"[^a-z0-9+/#]", " ", (text or "").lower()).split()
            if t and t not in _STOP and len(t) > 1]


def phrase_in(text, phrase):
    """Word-boundary phrase match. Bare `phrase in text` misfires on short
    tokens ('opt' in 'optimize', 'itar' in 'military', 'cpt' in ...), which for
    the eligibility gate would fabricate work-auth evidence or a false SKIP. A
    boundary match avoids that while still matching multi-word phrases."""
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])",
                     text) is not None


# -------------------------------------------------------------- eligibility ---
def eligibility(posting, profile):
    """HARD gate. Explicit posting language hard-stops regardless of any DOL
    sponsorship history. Returns (status, confidence, reason_codes, evidence).
    status in {ELIGIBLE, VERIFY, SKIP}."""
    text = " ".join(str(posting.get(k) or "") for k in
                    ("title", "full_description", "sponsorship_hint")).lower()
    ev = []
    for ph in profile["eligibility_block_phrases"]:
        if phrase_in(text, ph):
            ev.append(ph)
    hint = (posting.get("sponsorship_hint") or "").lower()
    if "citizen" in hint or "clearance" in hint:
        ev.append("tracker: " + posting.get("sponsorship_hint", ""))
    if ev:
        return "SKIP", "HIGH", ["POSTING_RESTRICTION"], ev
    if "does not offer sponsorship" in hint:
        # CPT-eligible for the internship itself, but a weak long-term signal.
        return ("VERIFY", "MEDIUM", ["NO_FUTURE_SPONSORSHIP"],
                ["tracker: Does Not Offer Sponsorship"])
    for ph in profile["eligibility_support_phrases"]:
        if phrase_in(text, ph):
            return "ELIGIBLE", "MEDIUM", ["POSTING_SUPPORTS_WORK_AUTH"], [ph]
    if "offers sponsorship" in hint:
        return "ELIGIBLE", "MEDIUM", ["OFFERS_SPONSORSHIP"], [hint]
    return "VERIFY", "LOW", ["MISSING_WORK_AUTH_EVIDENCE"], []


# ------------------------------------------------------------ role family -----
def classify(title, profile):
    t = (title or "").lower()
    for term in profile["out_of_scope_terms"]:
        if term in t:
            return "OUT_OF_SCOPE"
    for fam, kws in profile["role_family_lexicon"].items():
        if any(k in t for k in kws):
            return fam
    if "analyst" in t or "analytics" in t:
        return "ADJACENT_ANALYTICS"
    return "OUT_OF_SCOPE"


FAMILY_AFFINITY = {  # how close each family is to Ahaan's core profile
    "DATA_ANALYTICS": 1.0, "DATA_SCIENCE": 0.9, "BUSINESS_INTELLIGENCE": 0.85,
    "BUSINESS_ANALYTICS": 0.8, "ADJACENT_ANALYTICS": 0.55, "OUT_OF_SCOPE": 0.0,
}


# ---------------------------------------------------------- fit candidates ----
def build_idf(docs):
    n = len(docs)
    df = Counter()
    for d in docs:
        for w in set(d):
            df[w] += 1
    return {w: math.log((1 + n) / (1 + c)) + 1 for w, c in df.items()}


def tfidf_vec(tokens, idf):
    tf = Counter(tokens)
    return {w: (c / len(tokens)) * idf.get(w, 0) for w, c in tf.items()} \
        if tokens else {}


def cosine(a, b):
    if not a or not b:
        return 0.0
    dot = sum(v * b.get(k, 0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def fit_tfidf(posting, profile, ctx):
    doc = toks((posting.get("title") or "") + " " +
               (posting.get("full_description") or ""))
    return cosine(tfidf_vec(doc, ctx["idf"]), ctx["resume_vec"])


def fit_skilloverlap(posting, profile, ctx):
    text = ((posting.get("title") or "") + " " +
            (posting.get("full_description") or "")).lower()
    skills = profile["core_skills"]
    fam_kw = [k for kws in profile["role_family_lexicon"].values() for k in kws]
    hit_sk = sum(1 for s in skills if s in text)
    hit_fam = sum(1 for k in fam_kw if k in text)
    # normalise so a title (few tokens) can still reach a good score
    return min(1.0, 0.6 * hit_fam / 2 + 0.4 * hit_sk / 3)


def fit_rolefamily(posting, profile, ctx):
    return FAMILY_AFFINITY[classify(posting.get("title"), profile)]


FIT_CANDIDATES = {
    "tfidf_resume": fit_tfidf,
    "skill_overlap": fit_skilloverlap,
    "role_family": fit_rolefamily,
}


# ------------------------------------------------------------- combiners ------
def _logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def comb_additive(f, weights):
    # weighted mean of features in [0,1] — smooth and monotonic
    tot = sum(weights.values())
    return sum(weights[k] * f[k] for k in weights) / tot


def comb_multiplicative(f, weights):
    # weighted geometric mean — strongly penalises any weak feature, so a
    # posting cannot look strong on one axis alone (anti single-feature).
    tot = sum(weights.values())
    return math.exp(sum(weights[k] * math.log(0.05 + 0.95 * f[k])
                        for k in weights) / tot)


def comb_lexicographic(f, weights):
    # fit dominates; timing/network/access act only as bounded tie-breakers.
    return (0.70 * f["fit"] + 0.14 * f["timing"] +
            0.10 * f["network"] + 0.06 * f["access"])


COMBINERS = {
    "additive": comb_additive,
    "multiplicative": comb_multiplicative,
    "lexicographic": comb_lexicographic,
}
WEIGHTS = {"fit": 0.55, "timing": 0.18, "network": 0.15, "access": 0.12}

TIERS = ["WEAK MATCH", "ADJACENT", "GOOD MATCH", "STRONG MATCH"]


def to_tier(score):
    if score >= 0.62:
        return "STRONG MATCH"
    if score >= 0.47:
        return "GOOD MATCH"
    if score >= 0.32:
        return "ADJACENT"
    return "WEAK MATCH"


# --------------------------------------------------------- robustness harness -
def kendall_tau(x, y):
    n = len(x)
    if n < 2:
        return 1.0
    conc = disc = 0
    for i in range(n):
        for j in range(i + 1, n):
            s = (x[i] - x[j]) * (y[i] - y[j])
            if s > 0:
                conc += 1
            elif s < 0:
                disc += 1
    tot = conc + disc
    return (conc - disc) / tot if tot else 0.0


def evaluate_candidate(feats, combiner, weights, seed=2027, boot=160):
    """feats: list of {'fit','timing','network','access'} in [0,1].
    Returns robustness metrics for this (fit,combiner) pair."""
    rng = random.Random(seed)
    base_scores = [combiner(f, weights) for f in feats]
    base_tiers = [to_tier(s) for s in base_scores]

    # 1) bootstrap tier-stability under small input perturbation
    flip = 0
    for _ in range(boot):
        for f, bt in zip(feats, base_tiers):
            pert = {k: min(1.0, max(0.0, v + rng.gauss(0, 0.05)))
                    for k, v in f.items()}
            if to_tier(combiner(pert, weights)) != bt:
                flip += 1
    flip_rate = flip / (boot * len(feats)) if feats else 0.0

    # 2) Pareto consistency: dominated posting must never outscore a dominator
    keys = list(WEIGHTS)
    viol = pairs = 0
    for i in range(len(feats)):
        for j in range(len(feats)):
            if i == j:
                continue
            ge = all(feats[i][k] >= feats[j][k] for k in keys)
            gt = any(feats[i][k] > feats[j][k] for k in keys)
            if ge and gt:
                pairs += 1
                if base_scores[i] < base_scores[j] - 1e-9:
                    viol += 1
    pareto_violation_rate = viol / pairs if pairs else 0.0

    # 3) single-feature dominance: rank-corr of final order vs each feature.
    #    fit is EXPECTED to drive the order (that is its job); the V6 failure
    #    was an AUXILIARY, unvalidated feature silently controlling the result.
    #    So we report fit dominance for transparency but only penalise an
    #    auxiliary feature (timing/network/access) that dominates the order.
    dominance = {k: abs(kendall_tau(base_scores, [f[k] for f in feats]))
                 for k in keys}
    aux_dom = max((dominance[k] for k in ("timing", "network", "access")),
                  default=0.0)

    # 4) discrimination: a model that collapses every posting into one tier is
    #    maximally "stable" but useless. Reward genuine tier spread so
    #    non-discrimination is penalised (Part 3: features must discriminate).
    dist = Counter(base_tiers)
    max_share = max(dist.values()) / len(base_tiers) if base_tiers else 1.0
    discrimination = round(1.0 - max_share, 4)

    cost = (2.0 * flip_rate + 3.0 * pareto_violation_rate +
            1.5 * max(0.0, aux_dom - 0.60) + 1.5 * (1.0 - discrimination))
    return {
        "flip_rate": round(flip_rate, 4),
        "pareto_violation_rate": round(pareto_violation_rate, 4),
        "single_feature_dominance": {k: round(v, 3)
                                     for k, v in dominance.items()},
        "aux_feature_dominance": round(aux_dom, 4),
        "fit_dominance": round(dominance["fit"], 4),
        "discrimination": discrimination,
        "robustness_cost": round(cost, 4),
        "tier_distribution": dict(dist),
    }

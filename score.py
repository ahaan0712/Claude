#!/usr/bin/env python3
"""
Campaign 27 V7 - score.py

Scores each POSTING (not each company). This is the direct response to the
V6 diagnostics: V6 ranked 157 companies with a 7-feature simulation that
correlated 0.83 with a 3-rule heuristic, where weight-sampling contributed
~12 ranks of spread against ~49 from noisy feature values, and a single
unvalidated "Claude prior" silently drove ordering. None of that is
reproduced here. This script does not rank anything and does not output a
probability - it outputs, per posting:

  1. eligibility  - ELIGIBLE / VERIFY / INELIGIBLE / CLOSED (a gate, not a score)
  2. fit_score    - 0-100, resume/posting TF-IDF similarity x role-family match
  3. tier         - Strong / Good / Exploratory fit bucket (coarse, not a rank)
  4. timing       - days since posted + a decay multiplier already folded into fit
  5. preference   - the industry-preference multiplier that was applied

No probability of any outcome appears anywhere in this file. Probabilities
only ever come from calibrate.py, and only for lanes with >=20 logged
outcomes (see PRIOR-ONLY handling there and in portfolio.py).
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with", "at", "by",
    "is", "are", "be", "as", "this", "that", "will", "we", "you", "our", "your",
    "internship", "intern", "summer", "2027", "role", "position", "job", "team",
    "work", "opportunity", "candidate", "candidates", "student", "students",
}

TOKEN_RE = re.compile(r"[a-z][a-z0-9+/#\.]{1,}")


def tokenize(text: str) -> List[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS and len(t) > 1]


def tf_idf_cosine(doc_tokens: List[str], query_tokens: List[str], corpus_token_lists: List[List[str]]) -> float:
    """
    Minimal dependency-free TF-IDF cosine similarity between one posting's
    tokens and the resume's tokens, with IDF computed across the full
    posting corpus so common boilerplate (e.g. "summer", "apply", "team")
    doesn't dominate.
    """
    n_docs = max(len(corpus_token_lists), 1)
    df = Counter()
    for toks in corpus_token_lists:
        df.update(set(toks))

    def idf(term: str) -> float:
        return math.log((n_docs + 1) / (1 + df.get(term, 0))) + 1.0

    def vectorize(tokens: List[str]) -> Dict[str, float]:
        tf = Counter(tokens)
        vec = {t: (c / max(len(tokens), 1)) * idf(t) for t, c in tf.items()}
        return vec

    v1 = vectorize(doc_tokens)
    v2 = vectorize(query_tokens)
    if not v1 or not v2:
        return 0.0

    common = set(v1) & set(v2)
    dot = sum(v1[t] * v2[t] for t in common)
    norm1 = math.sqrt(sum(x * x for x in v1.values()))
    norm2 = math.sqrt(sum(x * x for x in v2.values()))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def role_family_match(posting_text: str, role_families: Dict[str, dict]) -> Tuple[Optional[str], float]:
    """
    Returns (best_family, multiplier). Multiplier follows the same shape as
    V4's role_fit effect (Excellent/Strong/Moderate/Weak/Unknown) but is
    derived from literal keyword overlap in the posting text, not a hidden
    per-company judgment call.
    """
    text = posting_text.lower()
    best_family, best_hits = None, 0
    for family, spec in role_families.items():
        hits = sum(1 for kw in spec["keywords"] if kw.lower() in text)
        if hits > best_hits:
            best_family, best_hits = family, hits
    if best_hits >= 2:
        return best_family, 1.25
    if best_hits == 1:
        return best_family, 1.0
    return None, 0.55  # no role-family keyword hit at all -> steep discount, not zero


def off_target_penalty(posting_text: str, off_target_keywords: List[str]) -> float:
    text = posting_text.lower()
    return 0.35 if any(kw.lower() in text for kw in off_target_keywords) else 1.0


def preference_multiplier(company: str, posting_text: str, profile: dict) -> float:
    text = (company + " " + posting_text).lower()
    pref = profile["preferred_industries"]["keywords"]
    deprio = profile["deprioritized_industries"]["keywords"]
    mult = 1.0
    if any(kw.lower() in text for kw in pref):
        mult *= 1.15
    if any(kw.lower() in text for kw in deprio):
        mult *= 0.6
    return mult


def timing_multiplier(date_posted: Optional[str], as_of: date) -> Tuple[Optional[int], float]:
    """
    Decay curve: <7 days is the documented edge (freshest postings get
    Ahaan's application first, before the pool of applicants deepens).
    Half-life of ~21 days after that; floor at 0.5 so an old-but-relevant
    posting is discounted, not erased. Unknown date -> neutral 0.85.
    """
    if not date_posted:
        return None, 0.85
    try:
        posted = datetime.strptime(date_posted, "%Y-%m-%d").date()
    except ValueError:
        return None, 0.85
    days = (as_of - posted).days
    if days < 0:
        days = 0
    if days <= 7:
        mult = 1.15
    else:
        mult = 0.55 + 0.60 * math.exp(-(days - 7) / 21.0)
    return days, max(mult, 0.5)


def eligibility_state(posting: dict, profile: dict) -> Tuple[str, str]:
    if posting.get("closed_badge"):
        return "CLOSED", "Tracker marked this posting closed."

    text = " ".join([posting.get("role", ""), posting.get("company", ""), posting.get("location", "")]).lower()

    if posting.get("us_citizen_badge"):
        return "INELIGIBLE", "Tracker badge: US citizens only. Ahaan is an F-1 international student."

    for phrase in profile["eligibility_block_phrases"]:
        if phrase.lower() in text:
            return "INELIGIBLE", f"Posting text matches a hard block phrase: \"{phrase}\"."

    if posting.get("no_sponsorship_badge"):
        return "INELIGIBLE", "Tracker badge: no visa sponsorship. Treated as a hard stop per V6 lesson (exact posting wording controls)."

    for phrase in profile["eligibility_verify_phrases"]:
        if phrase.lower() in text:
            return "VERIFY", f"Posting text mentions \"{phrase}\" - exact CPT/sponsorship wording must be checked on the live posting before applying."

    return "ELIGIBLE", "No CPT/OPT/sponsorship/citizenship block found in tracker data. Still verify on the live posting (trackers only capture company-level badges, not always the exact posting clause)."


def tier_for_fit(fit_score: float) -> str:
    if fit_score >= 65:
        return "Strong"
    if fit_score >= 40:
        return "Good"
    return "Exploratory"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postings", default=Path("data/postings.json"), type=Path)
    parser.add_argument("--profile", default=Path("data/profile.json"), type=Path)
    parser.add_argument("--out", default=Path("data/matches.json"), type=Path)
    parser.add_argument("--as-of", default=None, help="YYYY-MM-DD, defaults to today (UTC).")
    args = parser.parse_args()

    postings_payload = json.loads(args.postings.read_text(encoding="utf-8"))
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    postings = postings_payload["postings"]

    as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date() if args.as_of else date.today()

    resume_tokens = tokenize(profile["resume_text"])
    posting_texts = [f"{p['company']} {p['role']} {p.get('location','')}" for p in postings]
    corpus_token_lists = [tokenize(t) for t in posting_texts]

    matches = []
    counts = Counter()

    for posting, text, doc_tokens in zip(postings, posting_texts, corpus_token_lists):
        eligibility, eligibility_reason = eligibility_state(posting, profile)
        counts[eligibility] += 1

        family, family_mult = role_family_match(text, profile["role_families"])
        off_target_mult = off_target_penalty(text, profile["off_target_keywords"])
        pref_mult = preference_multiplier(posting["company"], text, profile)
        days_since_posted, timing_mult = timing_multiplier(posting.get("date_posted"), as_of)

        similarity = tf_idf_cosine(doc_tokens, resume_tokens, corpus_token_lists)
        raw_fit = similarity * family_mult * off_target_mult * pref_mult * timing_mult
        # scale to a readable 0-100 band; similarity alone rarely exceeds ~0.5
        # with TF-IDF on short posting text, so scale by a fixed constant
        # rather than min-max normalizing (min-max would silently re-rank
        # everything whenever the posting pool changes size/composition).
        fit_score = round(min(raw_fit * 220, 100.0), 1)

        matches.append({
            "posting_id": posting["posting_id"],
            "company": posting["company"],
            "role": posting["role"],
            "location": posting.get("location", ""),
            "url": posting.get("url"),
            "source": posting.get("source"),
            "date_posted": posting.get("date_posted"),
            "days_since_posted": days_since_posted,
            "eligibility": eligibility,
            "eligibility_reason": eligibility_reason,
            "role_family": family,
            "fit_score": fit_score,
            "fit_tier": tier_for_fit(fit_score),
            "components": {
                "resume_similarity_raw": round(similarity, 4),
                "role_family_multiplier": family_mult,
                "off_target_multiplier": off_target_mult,
                "preference_multiplier": round(pref_mult, 3),
                "timing_multiplier": round(timing_mult, 3),
            },
        })

    payload = {
        "scored_at": datetime.utcnow().isoformat() + "Z",
        "as_of_date": as_of.isoformat(),
        "posting_count": len(matches),
        "eligibility_counts": dict(counts),
        "note": "fit_score is a 0-100 relevance score, not a probability of any outcome. "
                "See calibrate.py / portfolio.py for the only probability estimates this "
                "project produces, and note they are PRIOR-ONLY until 20+ logged outcomes exist.",
        "matches": matches,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Scored {len(matches)} postings -> {args.out}")
    print("Eligibility breakdown:", dict(counts))


if __name__ == "__main__":
    main()

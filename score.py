#!/usr/bin/env python3
"""Part 3 — apply the eligibility gate + winning fit model to every posting.

Pipeline within this stage:
  1. compute the 4 transparent features per posting (fit x3 candidates,
     timing, network, access);
  2. run the robustness bake-off over every (fit candidate x combiner) pair
     and auto-select the most robust — writing data/model_report.json;
  3. apply the winner, assign eligibility state + fit TIER (never a point
     rank), and group the output for the viewer -> data/matches.json.

No probability and no rank is emitted. Every posting carries
calibration_status = PRIOR_ONLY until calibrate.py says otherwise.
"""
from __future__ import annotations
import json, datetime as dt
from pathlib import Path
from collections import Counter, defaultdict
from schema import write_json, now_iso
from companies import normalize_name
import model as M

TODAY = dt.date(2026, 7, 11)
FRIENDLY = {"STRONG": 1.0, "MODERATE": 0.6, "LOW": 0.3, "CLOSED": 0.0}
TIER_AFF = {"STRONG TARGET": 1.0, "TARGET": 0.75, "STRETCH": 0.5,
            "REACH": 0.3, "LONG SHOT": 0.15, None: 0.5}
NET_LEVEL = {"STRONG": 1.0, "MODERATE": 0.7, "WEAK": 0.45, "NONE": 0.25}


def load():
    raw = json.load(open("data/postings_raw.json"))["postings"]
    profile = json.load(open("data/profile.json"))
    comps = {normalize_name(c["company"]): c
             for c in json.load(open("data/companies.json"))["companies"]}
    net = {normalize_name(n["company"]): n
           for n in json.load(open("data/network_aggregates.json"))}
    return raw, profile, comps, net


def timing_feature(posting):
    d = posting.get("posting_date")
    if not d:
        return 0.5  # neutral, explicitly not a placeholder-as-fact
    try:
        age = (TODAY - dt.date.fromisoformat(d)).days
    except Exception:
        return 0.5
    if age <= 14:
        return 1.0
    if age >= 150:
        return 0.2
    return round(1.0 - 0.8 * (age - 14) / (150 - 14), 3)


def build_context(raw, profile):
    docs = [M.toks((p.get("title") or "") + " " +
                   (p.get("full_description") or "")) for p in raw]
    idf = M.build_idf(docs + [M.toks(profile["resume_text"])])
    resume_vec = M.tfidf_vec(M.toks(profile["resume_text"]), idf)
    return {"idf": idf, "resume_vec": resume_vec}


def features_for(posting, profile, comps, net, ctx):
    cid = normalize_name(posting.get("company", ""))
    comp = comps.get(cid)
    fits = {name: fn(posting, profile, ctx)
            for name, fn in M.FIT_CANDIDATES.items()}
    timing = timing_feature(posting)
    nlevel = net.get(cid, {}).get("networking_opportunity_level", "NONE")
    network = NET_LEVEL[nlevel]
    if comp:
        access = round(0.6 * FRIENDLY.get(comp["intl_friendly_level"], 0.6) +
                       0.4 * TIER_AFF.get(comp["manual_access_tier"], 0.5), 3)
    else:
        access = 0.4  # off-target-list company: known-neutral, flagged below
    return fits, {"timing": timing, "network": network, "access": access}, \
        comp, nlevel


def main():
    raw, profile, comps, net = load()
    ctx = build_context(raw, profile)

    # --- compute per-posting features + eligibility -----------------------
    records = []
    for p in raw:
        elig, conf, codes, ev = M.eligibility(p, profile)
        fam = M.classify(p.get("title"), profile)
        fits, other, comp, nlevel = features_for(p, profile, comps, net, ctx)
        records.append({
            "posting": p, "elig": elig, "conf": conf, "codes": codes,
            "elig_ev": ev, "family": fam, "fits": fits, "other": other,
            "comp": comp, "nlevel": nlevel,
            "on_target_list": comp is not None,
        })

    # in-scope = eligible-or-verify AND a real analytics-adjacent family
    scored_pool = [r for r in records
                   if r["elig"] != "SKIP" and r["family"] != "OUT_OF_SCOPE"]

    # --- robustness bake-off + auto-selection -----------------------------
    def feats_with(fitname):
        return [{"fit": r["fits"][fitname], **r["other"]} for r in scored_pool]

    results = {}
    for fitname in M.FIT_CANDIDATES:
        fv = feats_with(fitname)
        for cname, comb in M.COMBINERS.items():
            results[f"{fitname}+{cname}"] = M.evaluate_candidate(
                fv, comb, M.WEIGHTS)
    winner = min(results, key=lambda k: results[k]["robustness_cost"])
    win_fit, win_comb = winner.split("+")

    ranked = sorted(results.items(), key=lambda kv: kv[1]["robustness_cost"])
    losers = []
    for name, met in ranked[1:]:
        reason = []
        if met["pareto_violation_rate"] > results[winner][
                "pareto_violation_rate"] + 1e-9:
            reason.append("Pareto violations (ranked a dominated posting "
                          "above its dominator)")
        if met["flip_rate"] > results[winner]["flip_rate"] + 0.02:
            reason.append(f"less stable (tier flips {met['flip_rate']:.0%} vs "
                          f"{results[winner]['flip_rate']:.0%})")
        if met["discrimination"] < results[winner]["discrimination"] - 0.05:
            reason.append(f"weak discrimination (collapses postings; spread "
                          f"{met['discrimination']} vs "
                          f"{results[winner]['discrimination']})")
        if met["aux_feature_dominance"] > 0.60:
            worst = max(("timing", "network", "access"),
                        key=lambda k: met["single_feature_dominance"][k])
            reason.append(f"auxiliary feature '{worst}' over-controls the order "
                          f"(tau={met['single_feature_dominance'][worst]})")
        losers.append({"candidate": name,
                       "robustness_cost": met["robustness_cost"],
                       "why_it_lost": reason or ["higher overall robustness "
                                                 "cost"]})

    model_report = {
        "generated_at": now_iso(),
        "selection_basis": "MOST ROBUST, NOT MOST ACCURATE. Zero outcomes are "
        "logged, so real-world accuracy is unmeasurable. Winner minimises a "
        "cost of tier-flip instability, Pareto violations, and single-feature "
        "dominance (the V6 'Claude prior' failure mode).",
        "fit_candidates": list(M.FIT_CANDIDATES),
        "combiners": list(M.COMBINERS),
        "feature_weights": M.WEIGHTS,
        "winner": {"fit": win_fit, "combiner": win_comb,
                   "metrics": results[winner]},
        "all_candidates": results,
        "why_others_lost": losers,
        "postings_in_scope": len(scored_pool),
    }
    write_json("data/model_report.json", model_report)

    # --- apply winner -----------------------------------------------------
    comb = M.COMBINERS[win_comb]
    live, review, excluded = [], [], []
    for r in records:
        p = r["posting"]
        base = {
            "posting_id": _pid(p),
            "company": p.get("company"),
            "title": p.get("title"),
            "location": p.get("location"),
            "posting_date": p.get("posting_date"),
            "apply_url": p.get("apply_url"),
            "source": p.get("source"),
            "also_seen_in": p.get("also_seen_in", []),
            "role_family": r["family"],
            "eligibility_status": r["elig"],
            "eligibility_confidence": r["conf"],
            "eligibility_reason_codes": r["codes"],
            "eligibility_evidence": r["elig_ev"],
            "on_target_list": r["on_target_list"],
            "network_level": r["nlevel"],
            "calibration_status": "PRIOR_ONLY",
            "calibrated_probability": None,
        }
        if r["elig"] == "SKIP":
            base["fit_tier"] = None
            excluded.append(base)
            continue
        if r["family"] == "OUT_OF_SCOPE":
            continue  # not published; wrong role family for this candidate
        f = {"fit": r["fits"][win_fit], **r["other"]}
        score = comb(f, M.WEIGHTS)
        # tier only — the raw score stays in-memory and is deliberately NOT
        # published, so no within-tier numeric leaderboard can be reconstructed
        # from the JSON (Part 0 #4).
        base["fit_tier"] = M.to_tier(score)
        base["fit_reasons"] = _reasons(r, win_fit)
        (live if r["elig"] == "ELIGIBLE" else review).append(base)

    # group by eligibility state + fit tier (NO ranks)
    def grouped(items):
        g = defaultdict(lambda: defaultdict(list))
        for it in items:
            g[it["eligibility_status"]][it["fit_tier"]].append(it)
        # stable tier order, alpha within tier (never a numeric rank)
        order = {t: i for i, t in enumerate(reversed(M.TIERS))}
        return {es: {t: sorted(v, key=lambda x: (x["company"] or "",
                                                 x["title"] or ""))
                     for t, v in sorted(tiers.items(),
                                        key=lambda kv: order.get(kv[0], 9))}
                for es, tiers in g.items()}

    write_json("data/matches.json", {
        "schema_version": "campaign27.v7.1",
        "generated_at": now_iso(),
        "note": "Posting-level matches. Eligibility is a hard gate; fit is a "
        "grouped tier, never a rank or probability. All lanes are PRIOR_ONLY "
        "until 20+ outcomes are logged.",
        "model": {"fit": win_fit, "combiner": win_comb},
        "counts": {"eligible": len(live), "verify": len(review),
                   "excluded_skip": len(excluded)},
        "eligible": grouped(live),
        "verify": grouped(review),
        "excluded": excluded,
    })
    print(f"score: winner={winner} cost={results[winner]['robustness_cost']} "
          f"| eligible={len(live)} verify={len(review)} skip={len(excluded)}")


def _pid(p):
    import hashlib
    key = (normalize_name(p.get("company", "")) + "|" +
           (p.get("title") or "").lower() + "|" + (p.get("posting_date") or ""))
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def _reasons(r, win_fit):
    out = [f"role family: {r['family'].replace('_', ' ').title()}"]
    if r["fits"][win_fit] >= 0.5:
        out.append("strong resume/role-content overlap")
    if r["other"]["network"] >= 0.7:
        out.append(f"network: {r['nlevel'].lower()} connection presence")
    if r["other"]["timing"] >= 0.8:
        out.append("recently posted")
    if r["on_target_list"]:
        out.append("on your 162-company target list")
    return out


if __name__ == "__main__":
    main()

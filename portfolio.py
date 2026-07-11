#!/usr/bin/env python3
"""Part 0 #5 — the headline portfolio curve: apply to top N postings ->
expected interviews, with honest uncertainty bands.

Because ZERO outcomes are logged (Part 0 #3), this curve is built from the V4
generic role PRIORS, not from Ahaan's results. It is therefore labelled
PRIOR_ONLY everywhere and drawn with deliberately wide p10-p90 bands from the
prior logit uncertainty. It is an illustrative planning aid, not a calibrated
forecast, and says so in the data the viewer reads.
"""
from __future__ import annotations
import json, math, random
from pathlib import Path
from schema import write_json, now_iso
from calibrate import LANE_TO_V4
from ahaan_model_v4_update import ROLE_PRIORS, logistic, logit

TIER_ORDER = {"STRONG MATCH": 0, "GOOD MATCH": 1, "ADJACENT": 2,
              "WEAK MATCH": 3}


def flatten(matches):
    out = []
    for bucket in ("eligible", "verify"):
        for es, tiers in matches.get(bucket, {}).items():
            for tier, items in tiers.items():
                for it in items:
                    out.append((tier, it))
    out.sort(key=lambda x: (TIER_ORDER.get(x[0], 9),
                            x[1].get("company") or ""))
    return [it for _, it in out]


def main():
    cal = json.load(open("data/lane_calibration.json"))
    lane_status = {l["role_family"]: l["calibration_status"]
                   for l in cal["lanes"]}
    any_cal = any(s == "CALIBRATED" for s in lane_status.values())

    matches = json.load(open("data/matches.json")) \
        if Path("data/matches.json").exists() else {}
    postings = flatten(matches)

    # each posting -> its lane's prior (interview_rate, logit_sd)
    rng = random.Random(2027)
    per = []
    for it in postings:
        fam = it.get("role_family", "ADJACENT_ANALYTICS")
        v4 = LANE_TO_V4.get(fam, "Analytics Consulting")
        p, sd = ROLE_PRIORS[v4]
        per.append((p, sd))

    curve = []
    DRAWS = 2000
    # precompute cumulative MC samples of expected interview count
    sample_matrix = []
    for p, sd in per:
        base = logit(p)
        sample_matrix.append([logistic(rng.gauss(base, sd))
                              for _ in range(DRAWS)])
    for n in range(1, len(per) + 1):
        totals = [sum(sample_matrix[i][d] for i in range(n))
                  for d in range(DRAWS)]
        totals.sort()
        curve.append({
            "n_applications": n,
            "expected_interviews": round(sum(totals) / DRAWS, 3),
            "p10": round(totals[int(0.10 * DRAWS)], 3),
            "p90": round(totals[int(0.90 * DRAWS)], 3),
        })

    write_json("data/portfolio.json", {
        "schema_version": "campaign27.v7.1",
        "generated_at": now_iso(),
        "calibration_state": "CALIBRATED" if any_cal else "PRIOR_ONLY",
        "headline": "Apply to top N postings -> expected interviews",
        "disclaimer": "PRIOR_ONLY: this curve uses generic role-family priors, "
        "NOT your logged outcomes (you have zero). Bands are wide on purpose. "
        "Treat it as illustrative planning, not a calibrated forecast. It "
        "becomes real once you log 20 outcomes in a lane.",
        "n_postings": len(per),
        "curve": curve,
        "lane_calibration": cal["lanes"],
    })
    print(f"portfolio: PRIOR_ONLY curve over {len(per)} postings "
          f"(expected interviews at N={len(per)}: "
          f"{curve[-1]['expected_interviews'] if curve else 0})")


if __name__ == "__main__":
    main()

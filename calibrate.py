#!/usr/bin/env python3
"""Part 3 — lane calibration, wired to the original V4 Bayesian math.

The audit found calibrate.py had silently dropped the V4 machinery: the
legacy docstring claims this file imports ROLE_PRIORS / logit / logistic /
posterior_delta_grid from legacy/ahaan_model_v4_update.py, but the previous
implementation reimplemented a trivial counter and imported none of it. This
restores the real linkage so that WHEN outcomes exist the posterior is the V4
posterior — while keeping the hard honesty gate: a lane with fewer than 20
logged outcomes stays PRIOR_ONLY and publishes NO probability (Part 0 #3).

Lane labels map to the schema's PRIOR_ONLY/CALIBRATED (underscore); the legacy
module uses the 'PRIOR-ONLY' hyphen form, which is intentionally not written
into the pipeline JSON.
"""
from __future__ import annotations
import csv, sys, math
from pathlib import Path
from collections import defaultdict
from schema import write_json, now_iso

sys.path.insert(0, str(Path(__file__).parent / "legacy"))
from ahaan_model_v4_update import (  # noqa: E402  (legacy V4 reference math)
    ROLE_PRIORS, logistic, logit, posterior_delta_grid, quantile)

THRESHOLD = 20
# schema lane id -> V4 prior lane label
LANE_TO_V4 = {
    "DATA_ANALYTICS": "Data Analytics",
    "DATA_SCIENCE": "Applied Data Science",
    "BUSINESS_INTELLIGENCE": "Business Intelligence",
    "BUSINESS_ANALYTICS": "Strategy / Business Analytics",
    "ADJACENT_ANALYTICS": "Analytics Consulting",
}


def main():
    counts = defaultdict(lambda: {"applications": 0, "outcomes": []})
    if Path("data/outcomes.csv").exists():
        for r in csv.DictReader(open("data/outcomes.csv")):
            lane = r.get("role_family") or "DATA_ANALYTICS"
            counts[lane]["applications"] += 1
            v = r.get("interviewed")
            if v not in (None, ""):
                counts[lane]["outcomes"].append(
                    1 if str(v).strip() in ("1", "yes", "Yes", "TRUE", "True")
                    else 0)

    lanes = []
    for lane, v4lane in LANE_TO_V4.items():
        c = counts[lane]
        ys = c["outcomes"]
        n = len(ys)
        base_p, base_sd = ROLE_PRIORS[v4lane]
        # V4 posterior over the lane-specific logit shift delta
        delta_mean, delta_sd = posterior_delta_grid(ys)
        ready = n >= THRESHOLD
        entry = {
            "role_family": lane,
            "v4_prior_lane": v4lane,
            "prior_interview_rate": base_p,
            "prior_logit_sd": base_sd,
            "applications": c["applications"],
            "outcomes": n,
            "interviews": sum(ys),
            "posterior_logit_shift": round(delta_mean, 4),
            "posterior_shift_sd": round(delta_sd, 4),
            "calibration_status": "CALIBRATED" if ready else "PRIOR_ONLY",
            "outcomes_needed_for_calibration": max(0, THRESHOLD - n),
            # published probability ONLY when calibrated; else null (honesty gate)
            "calibrated_probability": (
                round(logistic(logit(base_p) + delta_mean), 4)
                if ready else None),
        }
        lanes.append(entry)

    write_json("data/lane_calibration.json", {
        "generated_at": now_iso(),
        "threshold": THRESHOLD,
        "method": "V4 Bayesian logit-shift posterior (legacy/"
        "ahaan_model_v4_update.py). Probabilities are withheld until a lane "
        "reaches 20 logged outcomes.",
        "message": "Expected-interview estimates are not available yet. Log 20 "
        "outcomes in a role lane to enable calibration.",
        "lanes": lanes,
    })
    ready = sum(1 for l in lanes if l["calibration_status"] == "CALIBRATED")
    print(f"calibrate: {ready}/{len(lanes)} lanes calibrated "
          f"(V4 math wired; all PRIOR_ONLY until 20 outcomes)")


if __name__ == "__main__":
    main()

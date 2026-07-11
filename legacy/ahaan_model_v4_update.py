#!/usr/bin/env python3
"""
Ahaan V4 Bayesian updater.

Inputs:
  roles.csv   - export from the workbook's Role Model sheet
  tracker.csv - export from the Application Tracker sheet

Outputs:
  personal_calibration.csv
  updated_role_probabilities.csv

The updater performs:
1. lane-level Bayesian logit calibration from Ahaan's labeled outcomes;
2. Monte Carlo propagation of prior and feature uncertainty;
3. credibility-tier assignment.

Only an explicit exact-posting CPT/work-authorization block creates a zero.

--- Campaign 27 V7 note ---
This file is kept verbatim as the original V4 reference. calibrate.py
imports ROLE_PRIORS, logistic, logit, posterior_delta_grid, and quantile
from this module rather than reimplementing the Bayesian math, and adapts
only the I/O layer to posting-level outcome logging (outcomes.csv) instead
of the workbook's roles.csv/tracker.csv export shape. Do not edit the
math in this file without re-deriving calibrate.py's assumptions.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

ROLE_PRIORS = {
    "Data Analytics": (0.045, 0.80),
    "Business Intelligence": (0.050, 0.80),
    "Product Analytics": (0.035, 0.85),
    "Decision Science": (0.030, 0.90),
    "Growth / Marketing Analytics": (0.040, 0.85),
    "Strategy / Business Analytics": (0.045, 0.80),
    "Analytics Consulting": (0.035, 0.90),
    "Economic Consulting": (0.030, 0.95),
    "Risk / Financial Analytics": (0.035, 0.90),
    "Applied Data Science": (0.030, 0.95),
}

EFFECTS = {
    "role_fit": {
        "Excellent": (math.log(1.60), 0.35),
        "Strong": (math.log(1.35), 0.35),
        "Moderate": (0.0, 0.30),
        "Weak": (math.log(0.65), 0.45),
        "Unknown": (0.0, 0.55),
    },
    "gpa": {
        "Meets / no threshold": (0.0, 0.15),
        "Below preferred": (math.log(0.85), 0.25),
        "Below stated minimum": (math.log(0.55), 0.45),
        "Unknown": (0.0, 0.30),
    },
    "internship": {
        "Direct analytics progression": (math.log(1.40), 0.30),
        "Related progression": (math.log(1.18), 0.25),
        "Little relevant experience": (math.log(0.78), 0.35),
        "Unknown": (0.0, 0.30),
    },
    "selectivity": {
        "Elite / tiny class": (math.log(0.50), 0.45),
        "Highly selective": (math.log(0.70), 0.35),
        "Typical large employer": (0.0, 0.30),
        "Broad / emerging program": (math.log(1.15), 0.30),
        "Unknown": (0.0, 0.55),
    },
    "timing": {
        "0–7 days": (math.log(1.20), 0.20),
        "8–21 days": (0.0, 0.15),
        "22+ days": (math.log(0.80), 0.25),
        "Unknown": (0.0, 0.25),
    },
    "network": {
        "None": (0.0, 0.15),
        "Weak connection": (math.log(1.12), 0.25),
        "Warm referral": (math.log(1.65), 0.40),
        "Strong advocate": (math.log(2.20), 0.50),
        "Unknown": (0.0, 0.30),
    },
    "pathway": {
        "None": (0.0, 0.15),
        "Virginia Tech": (math.log(1.10), 0.20),
        "ALSAC / St. Jude": (math.log(1.12), 0.25),
        "VT + ALSAC": (math.log(1.22), 0.30),
        "Unknown": (0.0, 0.25),
    },
}

def logistic(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)

def logit(p: float) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return math.log(p / (1 - p))

def read_csv(path: Path) -> List[dict]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def truthy_one(value: str) -> int:
    return 1 if str(value).strip() in {"1", "Yes", "yes", "TRUE", "True"} else 0

def lane_outcomes(tracker: Iterable[dict]) -> Dict[str, List[int]]:
    out: Dict[str, List[int]] = defaultdict(list)
    for row in tracker:
        lane = (row.get("Role family") or row.get("role_family") or "").strip()
        value = row.get("Interviewed (0/1)") or row.get("interviewed") or ""
        if lane and str(value).strip() in {"0", "1"}:
            out[lane].append(truthy_one(value))
    return out

def posterior_delta_grid(outcomes: List[int]) -> Tuple[float, float]:
    """
    Posterior for a lane-specific logit shift delta.
    Prior: delta ~ Normal(0, 1).
    Likelihood uses a centered reference probability of 4%.
    This is intentionally conservative and one-dimensional.
    """
    if not outcomes:
        return 0.0, 1.0

    grid = [(-3.0 + i * 0.01) for i in range(601)]
    base = logit(0.04)
    log_weights = []

    for delta in grid:
        lp = -0.5 * delta * delta  # N(0,1), constant omitted
        p = logistic(base + delta)
        p = min(max(p, 1e-9), 1 - 1e-9)
        lp += sum(y * math.log(p) + (1 - y) * math.log(1 - p) for y in outcomes)
        log_weights.append(lp)

    m = max(log_weights)
    weights = [math.exp(x - m) for x in log_weights]
    total = sum(weights)
    weights = [w / total for w in weights]

    mean = sum(x * w for x, w in zip(grid, weights))
    var = sum((x - mean) ** 2 * w for x, w in zip(grid, weights))
    return mean, math.sqrt(max(var, 1e-12))

def effect_draw(category: str, label: str) -> float:
    mean, sd = EFFECTS[category].get(label or "Unknown", EFFECTS[category]["Unknown"])
    return random.gauss(mean, sd)

def quantile(values: List[float], q: float) -> float:
    values = sorted(values)
    if not values:
        return float("nan")
    pos = (len(values) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return values[lo]
    return values[lo] * (hi - pos) + values[hi] * (pos - lo)

def simulate_role(row: dict, calibration: Dict[str, Tuple[float, float]], draws: int) -> dict:
    lane = (row.get("Role family") or row.get("role_family") or "Data Analytics").strip()
    base_p, base_sd = ROLE_PRIORS.get(lane, ROLE_PRIORS["Data Analytics"])

    cpt = (row.get("Explicit CPT/work-auth block?") or row.get("cpt_block") or "").strip()
    if cpt == "Yes":
        return {
            "role_id": row.get("Role ID") or row.get("role_id") or "",
            "company": row.get("Company") or row.get("company") or "",
            "role": row.get("Exact role title") or row.get("role") or "",
            "role_family": lane,
            "p10": 0.0,
            "median": 0.0,
            "p90": 0.0,
            "credibility": "INELIGIBLE",
        }

    delta_mean, delta_sd = calibration.get(lane, (0.0, 1.0))
    samples = []
    for _ in range(draws):
        eta = random.gauss(logit(base_p), base_sd)
        eta += effect_draw("role_fit", row.get("Role fit") or row.get("role_fit") or "Unknown")
        eta += effect_draw("gpa", row.get("GPA treatment") or row.get("gpa") or "Unknown")
        eta += effect_draw("internship", row.get("Internship progression") or row.get("internship") or "Unknown")
        eta += effect_draw("selectivity", row.get("Company selectivity") or row.get("selectivity") or "Unknown")
        eta += effect_draw("timing", row.get("Application timing") or row.get("timing") or "Unknown")
        eta += effect_draw("network", row.get("Network strength") or row.get("network") or "Unknown")
        eta += effect_draw("pathway", row.get("VT/ALSAC pathway") or row.get("pathway") or "Unknown")
        eta += random.gauss(delta_mean, delta_sd)
        samples.append(logistic(eta))

    comparable = int(float(row.get("Comparable positive profiles") or row.get("comparable_profiles") or 0))
    documented = int(float(row.get("Documented external outcomes") or row.get("documented_outcomes") or 0))
    ext_apps = int(float(row.get("External applications") or row.get("external_applications") or 0))
    ext_interviews = int(float(row.get("External interviews") or row.get("external_interviews") or 0))
    personal_n = int(float(row.get("Personal lane applications") or row.get("personal_applications") or 0))

    verified = (row.get("Posting verified?") or row.get("posting_verified") or "").strip() == "Yes"
    if personal_n >= 20 or documented >= 20 or (ext_apps >= 50 and ext_interviews > 0):
        tier = "DATA-BACKED"
    elif verified and (comparable >= 5 or documented >= 5 or ext_apps >= 25):
        tier = "PARTIALLY INFORMED"
    else:
        tier = "PRIOR-ONLY"

    return {
        "role_id": row.get("Role ID") or row.get("role_id") or "",
        "company": row.get("Company") or row.get("company") or "",
        "role": row.get("Exact role title") or row.get("role") or "",
        "role_family": lane,
        "p10": quantile(samples, 0.10),
        "median": quantile(samples, 0.50),
        "p90": quantile(samples, 0.90),
        "credibility": tier,
    }

def write_csv(path: Path, rows: List[dict], fields: List[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--roles", required=True, type=Path)
    parser.add_argument("--tracker", required=True, type=Path)
    parser.add_argument("--out-dir", default=Path("."), type=Path)
    parser.add_argument("--draws", default=20000, type=int)
    parser.add_argument("--seed", default=2027, type=int)
    args = parser.parse_args()

    random.seed(args.seed)
    roles = read_csv(args.roles)
    tracker = read_csv(args.tracker)
    outcomes = lane_outcomes(tracker)

    calibration: Dict[str, Tuple[float, float]] = {}
    calibration_rows = []
    for lane in ROLE_PRIORS:
        ys = outcomes.get(lane, [])
        mean, sd = posterior_delta_grid(ys)
        calibration[lane] = (mean, sd)
        n = len(ys)
        interviews = sum(ys)
        tier = "DATA-BACKED" if n >= 20 else ("PARTIALLY INFORMED" if n >= 5 else "PRIOR-ONLY")
        calibration_rows.append({
            "role_family": lane,
            "applications": n,
            "interviews": interviews,
            "raw_interview_rate": (interviews / n) if n else "",
            "posterior_logit_shift": mean,
            "posterior_shift_sd": sd,
            "credibility": tier,
        })

    results = [simulate_role(row, calibration, args.draws) for row in roles if any(row.values())]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        args.out_dir / "personal_calibration.csv",
        calibration_rows,
        ["role_family", "applications", "interviews", "raw_interview_rate",
         "posterior_logit_shift", "posterior_shift_sd", "credibility"],
    )
    write_csv(
        args.out_dir / "updated_role_probabilities.csv",
        results,
        ["role_id", "company", "role", "role_family", "p10", "median", "p90", "credibility"],
    )

if __name__ == "__main__":
    main()

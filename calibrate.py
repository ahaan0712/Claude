#!/usr/bin/env python3
"""
Campaign 27 V7 - calibrate.py

Wraps the existing V4 Bayesian lane updater (legacy/ahaan_model_v4_update.py)
instead of reimplementing it. Reuses ROLE_PRIORS, logistic/logit, and
posterior_delta_grid unchanged; only the I/O layer is new, because V7 logs
outcomes per posting (outcomes.csv) rather than exporting the workbook's
roles.csv/tracker.csv sheets.

Input: data/outcomes.csv, one row per posting Ahaan actually applied to:
    posting_id, company, role, role_family, applied (0/1), interviewed (0/1), date

Output: data/lane_calibration.json - one entry per role-family lane with:
  - n (applications logged), interviews, raw_interview_rate  (always shown - these are just counts)
  - credibility: "DATA-BACKED" (n >= 20) or "PRIOR-ONLY" (n < 20)
  - published_probability: {p10, median, p90} - ONLY present when DATA-BACKED
  - reference_prior: {p10, median, p90} - the V4 ROLE_PRIORS band, explicitly
    labeled as an unvalidated prior, never surfaced as a probability. Kept only
    so portfolio.py has something honest to propagate uncertainty from for
    PRIOR-ONLY lanes.

Hard rule enforced here: a lane never gets a "published_probability" field
with fewer than 20 logged outcomes. There is no fallback path that fabricates
one - PRIOR-ONLY lanes get reference_prior instead, and portfolio.py /
app.html must keep that distinction visible.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent / "legacy"))
from ahaan_model_v4_update import (  # noqa: E402
    ROLE_PRIORS,
    logistic,
    logit,
    posterior_delta_grid,
    quantile,
)

DATA_BACKED_THRESHOLD = 20


def read_outcomes(path: Path) -> Dict[str, List[int]]:
    """Returns {role_family: [interviewed 0/1, ...]} over applied postings."""
    lanes: Dict[str, List[int]] = defaultdict(list)
    if not path.exists():
        return lanes
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            lane = (row.get("role_family") or "").strip()
            applied = str(row.get("applied") or "").strip() in {"1", "Yes", "yes", "TRUE", "True"}
            interviewed_raw = str(row.get("interviewed") or "").strip()
            if not lane or not applied or interviewed_raw == "":
                continue
            interviewed = 1 if interviewed_raw in {"1", "Yes", "yes", "TRUE", "True"} else 0
            lanes[lane].append(interviewed)
    return lanes


def prior_band(lane: str, draws: int, seed: int) -> Dict[str, float]:
    rng = random.Random(seed)
    base_p, base_sd = ROLE_PRIORS.get(lane, ROLE_PRIORS["Data Analytics"])
    samples = [logistic(rng.gauss(logit(base_p), base_sd)) for _ in range(draws)]
    return {
        "p10": round(quantile(samples, 0.10), 4),
        "median": round(quantile(samples, 0.50), 4),
        "p90": round(quantile(samples, 0.90), 4),
    }


def posterior_band(lane: str, outcomes: List[int], draws: int, seed: int) -> Dict[str, float]:
    rng = random.Random(seed)
    base_p, base_sd = ROLE_PRIORS.get(lane, ROLE_PRIORS["Data Analytics"])
    delta_mean, delta_sd = posterior_delta_grid(outcomes)
    samples = [
        logistic(rng.gauss(logit(base_p), base_sd) + rng.gauss(delta_mean, delta_sd))
        for _ in range(draws)
    ]
    return {
        "p10": round(quantile(samples, 0.10), 4),
        "median": round(quantile(samples, 0.50), 4),
        "p90": round(quantile(samples, 0.90), 4),
    }, delta_mean, delta_sd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outcomes", default=Path("data/outcomes.csv"), type=Path)
    parser.add_argument("--out", default=Path("data/lane_calibration.json"), type=Path)
    parser.add_argument("--draws", default=20000, type=int)
    parser.add_argument("--seed", default=2027, type=int)
    args = parser.parse_args()

    lane_outcomes = read_outcomes(args.outcomes)
    lanes_seen = set(ROLE_PRIORS) | set(lane_outcomes)

    lanes_out = {}
    for lane in sorted(lanes_seen):
        outcomes = lane_outcomes.get(lane, [])
        n = len(outcomes)
        interviews = sum(outcomes)
        entry = {
            "n_applications_logged": n,
            "interviews": interviews,
            "raw_interview_rate": round(interviews / n, 4) if n else None,
        }
        if n >= DATA_BACKED_THRESHOLD:
            band, delta_mean, delta_sd = posterior_band(lane, outcomes, args.draws, args.seed)
            entry.update({
                "credibility": "DATA-BACKED",
                "published_probability": band,
                "posterior_logit_shift_mean": round(delta_mean, 4),
                "posterior_logit_shift_sd": round(delta_sd, 4),
            })
        else:
            entry.update({
                "credibility": "PRIOR-ONLY",
                "published_probability": None,
                "reference_prior": prior_band(lane, args.draws, args.seed),
                "reference_prior_note": (
                    "V4's unvalidated role-family prior, shown for transparency only. "
                    "Not a probability - do not display as one. Needs "
                    f"{DATA_BACKED_THRESHOLD - n} more logged outcomes in this lane to publish one."
                ),
            })
        lanes_out[lane] = entry

    payload = {
        "calibrated_at": datetime.utcnow().isoformat() + "Z",
        "data_backed_threshold": DATA_BACKED_THRESHOLD,
        "total_applications_logged": sum(len(v) for v in lane_outcomes.values()),
        "lanes": lanes_out,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    data_backed = [l for l, e in lanes_out.items() if e["credibility"] == "DATA-BACKED"]
    print(f"Calibrated {len(lanes_out)} lanes -> {args.out}")
    print(f"DATA-BACKED lanes ({len(data_backed)}): {data_backed or 'none yet'}")
    print(f"All other lanes are PRIOR-ONLY (need {DATA_BACKED_THRESHOLD}+ logged outcomes each).")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Campaign 27 V7 - portfolio.py

Headline output: "apply to top N postings -> expected interviews," with
honest uncertainty bands. This deliberately does NOT rank companies or
postings for display - "top N" is only an internal ordering (by fit_score,
eligible postings only) used to decide which postings accumulate into the
curve as N grows.

Hard rule: a posting only contributes to the CALIBRATED curve if its
role-family lane is DATA-BACKED (>=20 logged outcomes, per calibrate.py).
Postings in PRIOR-ONLY lanes are never blended into the calibrated headline
number - that would be exactly the kind of fabricated probability this
project exists to avoid. They instead populate a separate, clearly-labeled
"illustrative PRIOR-ONLY curve" built from V4's unvalidated role priors, so
the tool still gives Ahaan something useful before any outcomes are logged,
without ever letting an unvalidated guess masquerade as a calibrated one.

Uncertainty bands come from a Monte Carlo draw per lane (shared across every
posting in that lane, so correlated lane-level error is preserved) plus a
Bernoulli realization draw per posting - this is a predictive distribution
over "how many interviews would Ahaan actually get," not just a point mean.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent / "legacy"))
from ahaan_model_v4_update import ROLE_PRIORS, logistic, logit, posterior_delta_grid  # noqa: E402

DRAWS = 3000


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_lane_p_draws(lane: str, credibility: str, calib_entry: Optional[dict],
                        outcomes: List[int], rng: random.Random, draws: int) -> List[float]:
    base_p, base_sd = ROLE_PRIORS.get(lane, ROLE_PRIORS["Data Analytics"])
    if credibility == "DATA-BACKED":
        delta_mean, delta_sd = posterior_delta_grid(outcomes)
    else:
        delta_mean, delta_sd = 0.0, 0.0  # no outcome-driven shift for PRIOR-ONLY lanes
    return [logistic(rng.gauss(logit(base_p), base_sd) + rng.gauss(delta_mean, delta_sd)) for _ in range(draws)]


def quantile(values: List[float], q: float) -> float:
    values = sorted(values)
    n = len(values)
    if n == 0:
        return float("nan")
    pos = (n - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, n - 1)
    frac = pos - lo
    return values[lo] * (1 - frac) + values[hi] * frac


def build_curve(ordered_postings: List[dict], lane_p_draws: Dict[str, List[float]],
                 rng: random.Random, draws: int, breakpoints: List[int]) -> List[dict]:
    cumulative = [0] * draws
    curve = []
    bp_set = set(breakpoints)
    for i, posting in enumerate(ordered_postings, start=1):
        p_draws = lane_p_draws[posting["role_family"]]
        for d in range(draws):
            if rng.random() < p_draws[d]:
                cumulative[d] += 1
        if i in bp_set:
            curve.append({
                "n_postings": i,
                "expected_interviews_mean": round(sum(cumulative) / draws, 3),
                "p10": round(quantile(cumulative, 0.10), 3),
                "median": round(quantile(cumulative, 0.50), 3),
                "p90": round(quantile(cumulative, 0.90), 3),
            })
    return curve


def make_breakpoints(total: int) -> List[int]:
    if total == 0:
        return []
    step = 5
    points = list(range(step, total, step))
    if not points or points[-1] != total:
        points.append(total)
    return points


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matches", default=Path("data/matches.json"), type=Path)
    parser.add_argument("--calibration", default=Path("data/lane_calibration.json"), type=Path)
    parser.add_argument("--outcomes", default=Path("data/outcomes.csv"), type=Path)
    parser.add_argument("--out", default=Path("data/portfolio.json"), type=Path)
    parser.add_argument("--seed", default=2027, type=int)
    args = parser.parse_args()

    matches_payload = load_json(args.matches)
    calibration_payload = load_json(args.calibration)
    lanes_meta = calibration_payload["lanes"]

    # reload per-lane raw outcome lists (needed to regenerate posterior draws;
    # lane_calibration.json intentionally stores only summary quantiles, not
    # the full outcome list, to keep that file small and stable)
    from calibrate import read_outcomes  # local import to reuse the exact same parser
    lane_outcomes = read_outcomes(args.outcomes)

    eligible = [m for m in matches_payload["matches"] if m["eligibility"] == "ELIGIBLE"]
    unassigned = [m for m in eligible if not m.get("role_family")]
    assigned = [m for m in eligible if m.get("role_family")]
    assigned.sort(key=lambda m: (-m["fit_score"], m.get("days_since_posted") if m.get("days_since_posted") is not None else 9999, m["company"]))

    data_backed_lanes = sorted(l for l, e in lanes_meta.items() if e["credibility"] == "DATA-BACKED")
    prior_only_lanes = sorted(l for l, e in lanes_meta.items() if e["credibility"] == "PRIOR-ONLY")

    rng = random.Random(args.seed)
    lane_p_draws: Dict[str, List[float]] = {}
    for lane in sorted(set(m["role_family"] for m in assigned)):
        credibility = lanes_meta.get(lane, {}).get("credibility", "PRIOR-ONLY")
        lane_p_draws[lane] = build_lane_p_draws(lane, credibility, lanes_meta.get(lane), lane_outcomes.get(lane, []), rng, DRAWS)

    calibrated_pool = [m for m in assigned if m["role_family"] in data_backed_lanes]
    prior_only_pool = [m for m in assigned if m["role_family"] in prior_only_lanes]

    calibrated_curve = build_curve(calibrated_pool, lane_p_draws, rng, DRAWS, make_breakpoints(len(calibrated_pool)))
    prior_only_curve = build_curve(prior_only_pool, lane_p_draws, rng, DRAWS, make_breakpoints(len(prior_only_pool)))

    total_logged = calibration_payload.get("total_applications_logged", 0)
    if data_backed_lanes:
        basis = "PARTIAL" if prior_only_lanes else "FULLY_CALIBRATED"
    else:
        basis = "NO_CALIBRATED_LANES"

    if basis == "NO_CALIBRATED_LANES":
        headline = (
            f"0 of {len(lanes_meta)} role-family lanes are DATA-BACKED yet "
            f"({total_logged} outcomes logged so far; each lane needs 20+). "
            "No calibrated expected-interviews estimate can be published. "
            "The curve below is PRIOR-ONLY - built from V4's unvalidated role priors - "
            "and must not be read as a probability."
        )
    elif basis == "PARTIAL":
        headline = (
            f"{len(data_backed_lanes)} of {len(lanes_meta)} lanes are DATA-BACKED "
            f"({', '.join(data_backed_lanes)}). The calibrated curve below only counts postings "
            f"in those lanes ({len(calibrated_pool)} eligible postings). "
            f"{len(prior_only_pool)} eligible postings remain in PRIOR-ONLY lanes and are kept "
            "in a separate illustrative curve, not blended into the calibrated headline."
        )
    else:
        headline = (
            f"All {len(lanes_meta)} lanes are DATA-BACKED. Calibrated curve covers all "
            f"{len(calibrated_pool)} eligible, role-family-matched postings."
        )

    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "basis": basis,
        "headline": headline,
        "eligible_posting_count": len(eligible),
        "postings_excluded_no_role_family": len(unassigned),
        "data_backed_lanes": data_backed_lanes,
        "prior_only_lanes": prior_only_lanes,
        "calibrated_curve": calibrated_curve,
        "calibrated_curve_note": "Expected interviews from applying to the top N eligible, DATA-BACKED-lane postings ranked by fit_score. Empty until a lane crosses 20 logged outcomes.",
        "prior_only_curve": prior_only_curve,
        "prior_only_curve_note": "ILLUSTRATIVE ONLY. Built from V4's unvalidated role-family priors for lanes with fewer than 20 logged outcomes. Not a probability - do not present as one.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote portfolio curve -> {args.out}")
    print(headline)


if __name__ == "__main__":
    main()

"""V16.2: historical object-MAE risk, calibrated on strictly earlier dates."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

METRICS = ["mae_pp", "centered_mae_pp", "national_mae_pp", "canton_mae_pp"]
LEVELS = (.8, .9)
MODES = ("fixed", "expanding")
METHODS = ("date_mean", "pooled_object", "date_max")
WARMUP = 9
EXPECTED = 6.955753873756506
EXPECTED_SHA = "622654c965648400469066ac36ee5bb3b886f120d3124f0c786f533275e17089"


def upper(values, level):
    values = np.sort(np.asarray(values, dtype=float))
    if not len(values) or not np.isfinite(values).all() or not 0 < level < 1:
        raise ValueError("invalid calibration")
    k = math.ceil((len(values) + 1) * level)
    if k > len(values):
        raise ValueError("insufficient calibration units")
    return float(values[k - 1])


def validate(panel):
    p = panel.copy()
    p["vote_date"] = pd.to_datetime(p.vote_date, errors="raise")
    if (p.vote_date.isna().any() or p.vote_id.isna().any()
            or p.vote_id.duplicated().any()
            or p.vote_date.lt("2016-01-01").any()
            or p.vote_date.ge("2023-01-01").any()
            or not np.isfinite(p.mae_pp).all()
            or not p.mae_pp.between(0, 100).all()
            or p.vote_date.nunique() <= WARMUP):
        raise ValueError("invalid historical panel")
    return p.sort_values(["vote_date", "vote_id"])


def calibrate(panel):
    p = validate(panel)
    dates = sorted(p.vote_date.unique())
    rows = []
    for i, day in enumerate(dates[WARMUP:], WARMUP):
        current = p[p.vote_date.eq(day)]
        for mode in MODES:
            historical = p[p.vote_date.lt(dates[WARMUP] if mode == "fixed" else day)]
            assert historical.vote_date.max() < day
            grouped = historical.groupby("vote_date").mae_pp
            values = {"date_mean": grouped.mean(), "date_max": grouped.max(),
                      "pooled_object": historical.mae_pp}
            for level in LEVELS:
                for method in METHODS:
                    bound = upper(values[method], level)
                    for case in current.itertuples():
                        rows.append({"vote_date": str(pd.Timestamp(day).date()),
                                     "vote_id": str(case.vote_id), "mode": mode,
                                     "method": method, "level": level,
                                     "training_dates": int(historical.vote_date.nunique()),
                                     "training_units": len(values[method]),
                                     "bound_pp": bound, "mae_pp": float(case.mae_pp),
                                     "covered": bool(case.mae_pp <= bound)})
    return pd.DataFrame(rows)


def date_bootstrap(groups, seed=162, draws=5000):
    # Whole dates sampled together, preserving object count within each date.
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(groups), size=(draws, len(groups)))
    total = groups.objects.to_numpy()[idx].sum(axis=1)
    coverage = groups.covered.to_numpy()[idx].sum(axis=1) / total
    simultaneous = groups.all_covered.to_numpy()[idx].mean(axis=1)
    return {"object_coverage_ci": np.quantile(coverage, [.025, .975]).tolist(),
            "simultaneous_date_coverage_ci": np.quantile(simultaneous, [.025, .975]).tolist()}


def summarize(detail):
    result = []
    for (level, mode, method), g in detail.groupby(["level", "mode", "method"]):
        d = g.groupby("vote_date").agg(objects=("covered", "size"),
                                      covered=("covered", "sum"),
                                      all_covered=("covered", "all"),
                                      bound=("bound_pp", "first"),
                                      date_mean=("mae_pp", "mean"))
        result.append({"level": float(level), "mode": mode, "method": method,
                       "dates": len(d), "objects": len(g),
                       "covered_objects": int(g.covered.sum()),
                       "all_covered_dates": int(d.all_covered.sum()),
                       "covered_date_means": int((d.date_mean <= d.bound).sum()),
                       "mean_upper_pp_date": float(d.bound.mean()),
                       "mean_upper_pp_object": float(g.bound_pp.mean()),
                       **date_bootstrap(d)})
    return result


def run(source, output):
    from scripts.modeling.ensemble_v1010 import artifact_root, read_artifact
    from scripts.modeling.semantic_poll_comparison_v4 import sha
    root = artifact_root(source)
    if sha(root / "predictions.parquet") != EXPECTED_SHA:
        raise ValueError("Unexpected immutable predictions")
    frame = read_artifact(source, ["yes_share", "institution_text"]).reset_index()
    if not np.isfinite(frame[["yes_share", "institution_text"]]).all().all() or not (
        frame.yes_share.between(0, 1).all() and frame.institution_text.between(0, 1).all()
    ):
        raise ValueError("Invalid shares")
    frame["abs_error"] = 100 * (frame.yes_share - frame.institution_text).abs()
    panel = frame.groupby(["vote_date", "vote_id"], as_index=False).abs_error.mean()
    panel = panel.rename(columns={"abs_error": "mae_pp"})
    original = pd.read_csv(root / "object_metrics.csv", dtype={"vote_id": str})
    original = original[original.variant.eq("institution_text")].copy()
    original.vote_date = pd.to_datetime(original.vote_date)
    matched = panel.merge(original[["vote_date", "vote_id", *METRICS]],
                          on=["vote_date", "vote_id"], validate="one_to_one",
                          suffixes=("", "_original"))
    if (len(matched) != len(original) or len(matched) != 66
            or panel.vote_date.nunique() != 23
            or not np.allclose(matched.mae_pp, matched.mae_pp_original, atol=1e-8, rtol=0)
            or not np.isclose(panel.mae_pp.mean(), EXPECTED, atol=1e-8, rtol=0)):
        raise ValueError("Population or reference MAE mismatch")
    detail = calibrate(panel)
    result = {"status": "complete", "prediction_model_changed": False,
              "prediction_sha256": EXPECTED_SHA,
              "object_metrics_sha256": sha(root / "object_metrics.csv"),
              "source_run": 45444093555, "source_artifact": 14945871233,
              "population": {"rows": len(frame), "objects": len(panel),
                             "dates": int(panel.vote_date.nunique())},
              "historical_metrics_pp": {k: float(matched[k].mean()) for k in METRICS},
              "warmup_dates": WARMUP, "evaluation": summarize(detail),
              "bootstrap": {"draws": 5000, "seed": 162, "unit": "date",
                            "interpretation": "descriptive only; reused development dates"}}
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("preserve existing results")
    output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output / "object_risk.csv", index=False)
    (output / "manifest.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    print("SUMMARY", json.dumps(result, allow_nan=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)

"""Walk-forward calibration of national and linguistic-region poll margins.

Reuses immutable V8 predictions; past outcomes may calibrate future dates
only. No current or same-day outcomes enter a forecast. This is a rolling
development audit, not a new independent test or a model deployment.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear

from scripts.common.config import ROOT
from scripts.modeling.audit_xgboost_capacity import diagnostics
from scripts.modeling.regional_anchor_v8 import (
    LANGUAGES,
    REGIONS,
    gap_adjust,
    group_stats,
    load_regional,
    regional_target,
    shift_to,
)
from scripts.modeling.semantic_poll_comparison_v4 import paired_date_bootstrap, sha
from scripts.modeling.semantic_training_v5 import (
    CURRENT_POLLS,
    EXTRAS,
    HISTORICAL,
    HISTORICAL_POLLS,
    PLAN,
    V4,
    load_expanded_polls,
    prepare_data,
)

# Candidate national calibrations are fixed, not chosen on outer scores.
NATIONAL = (
    "frozen", "latest", "decided_latest", "decided_trend", "half_trend",
    "bias_shrink", "bounded_ridge",
)
REGIONAL = ("none", "decided_gap", "empirical_gap")
MIN_HISTORY = 8


def prior_poll_data(rows, date):
    """National raw measurements, with two-wave extrapolation and caps."""
    vote = pd.Timestamp(date)
    pub = pd.to_datetime(rows.published_at, utc=True)
    available = rows[pub.le(vote.tz_localize("UTC") - pd.Timedelta(days=1))].sort_values("wave")
    if available.empty:
        return None
    latest = available.iloc[-1]
    y = float(latest.yes_total) / 100
    n = float(latest.no_total) / 100
    u = float(latest.undecided) / 100
    d = y / (y + n)
    latest_date = pd.Timestamp(latest.survey_midpoint)
    delta = decided_delta = 0.
    if len(available) >= 2:
        prior = available.iloc[-2]
        t = (latest_date - pd.Timestamp(prior.survey_midpoint)).days
        remaining = (vote - latest_date).days
        if t <= 0 or remaining <= 0:
            raise ValueError("Invalid poll chronology")
        delta = float(np.clip((y - float(prior.yes_total)/100)*remaining/t, -.15, .15))
        p = float(prior.yes_total) / (float(prior.yes_total) + float(prior.no_total))
        decided_delta = float(np.clip((d - p)*remaining/t, -.15, .15))
    # Same feasible transfer constraints as the frozen national trend.
    delta = float(np.clip(delta, max(-y, n - 1), min(1-y, n)))
    return {"yes": y, "undecided": u, "delta": delta,
            "decided": d, "decided_delta": decided_delta,
            "frozen": float(np.clip(y + delta, 0, 1))}


def fit_national(history):
    """Bounded calibration with prior centered on the frozen correction.

    Predict observed proxy-weighted support minus raw latest yes. Fit the
    trend multiplier, allocation of undecided and intercept with bounded
    ridge: pseudo-data regularize against unstable fits on very few votes.
    """
    if len(history) < MIN_HISTORY:
        return np.array([0., 1., 0.]), 0.
    features = np.array([[1., h["delta"], h["undecided"]] for h in history])
    target = np.array([h["actual"] - h["yes"] for h in history])
    prior = np.array([0., 1., 0.])
    penalty = np.diag([np.sqrt(8.), .20, .20])
    result = lsq_linear(np.vstack([features, penalty]),
                        np.concatenate([target, penalty @ prior]),
                        bounds=([-0.15, 0., 0.], [.15, 1.5, 1.]))
    errors = np.array([h["actual"] - h["frozen"] for h in history])
    bias = float(errors.sum() / (len(errors)+8))
    return result.x, bias


def national_target(x, mode, fitted, bias, frozen):
    if mode == "frozen":
        return frozen
    if mode == "latest":
        return x["yes"]
    if mode == "decided_latest":
        return x["decided"]
    if mode == "decided_trend":
        return x["decided"] + x["decided_delta"]
    if mode == "half_trend":
        return x["frozen"] + .5*x["undecided"]
    if mode == "bias_shrink":
        return x["frozen"] + bias
    if mode == "bounded_ridge":
        return x["yes"] + fitted @ np.array([1., x["delta"], x["undecided"]])
    raise ValueError("Unknown national calibrator")


def fit_regional(history):
    """Empirical regional calibration of *contrasts*, not national levels.

    Fit one shared shrinkage slope and small region intercepts with a
    ridge prior around using published contrasts as-is. Marginal poll
    counts are not assumed to be independent or exact effective n.
    """
    if len(history) < MIN_HISTORY:
        return 1., np.zeros(3)
    x = np.vstack([h["poll_gap"] for h in history])
    y = np.vstack([h["actual_gap"] for h in history])
    # Fit a shared slope; regularize around 1, then estimate region-wise
    # residual offsets with 8 pseudo-objects of zero bias.
    slope = float(np.clip((np.sum(x*y) + .08)/(np.sum(x*x)+.08), .25, 1.5))
    intercept = (y-slope*x).sum(axis=0)/(len(history)+8)
    return slope, intercept


def run(base, prediction_dir, regional_path, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve previous experiments")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    data, _, _, _, _ = prepare_data(
        base, EXTRAS, HISTORICAL, V4, CURRENT_POLLS, HISTORICAL_POLLS, plan
    )
    national = load_expanded_polls(CURRENT_POLLS, HISTORICAL_POLLS)
    national["vote_key"] = national.vote_key.astype(str)
    regional = load_regional(regional_path, pd.read_csv(CURRENT_POLLS, dtype={"vote_key": str}))
    typology = pd.read_parquet(ROOT / "data/processed/typologies/commune_typologies.parquet",
                               columns=["municipality_id", "language_region"])
    typology["municipality_id"] = typology.municipality_id.astype(str)
    data["municipality_id"] = data.municipality_id.astype(str)
    data = data.merge(typology, on="municipality_id", validate="many_to_one", how="left")
    data["language"] = data.language_region.astype(str).map(REGIONS).fillna("other")
    data["weight"] = (data.statpop_pop_total*(1-data.statpop_share_foreign)*
                      (1-data.statpop_share_0_19)).fillna(0)
    manifest = json.loads((prediction_dir / "manifest.json").read_text(encoding="utf-8"))
    checksum = manifest["prediction_hashes"]["pca_recent5"]
    pred_path = prediction_dir / "pca_recent5_predictions.parquet"
    if sha(pred_path) != checksum:
        raise ValueError("Frozen V7 predictions changed")
    pred = pd.read_parquet(pred_path)
    pred["vote_id"], pred["municipality_id"] = pred.vote_id.astype(str), pred.municipality_id.astype(str)
    if len(pred) != 138868 or pred.vote_date.ge("2023-01-01").any():
        raise ValueError("Wrong evaluation population")
    # Include only past polled historical votes, including before the first
    # evaluation date; update after every entire day, never within the day.
    by_vote = {str(k): v.sort_values("municipality_id")
               for k, v in data.groupby("vote_id", sort=False)}
    poll_groups = {str(k): v for k,v in national.groupby("vote_key")}
    region_groups = {str(k): v for k,v in regional.groupby("vote_key")}
    prediction_groups = {str(k): v.sort_values("municipality_id")
                         for k,v in pred.groupby("vote_id")}
    outcome_dates = data[["vote_id","vote_date"]].drop_duplicates().sort_values("vote_date")
    history, regional_history, records, calibration = [], [], [], []
    for date, same_day in outcome_dates.groupby("vote_date", sort=True):
        coeff, bias = fit_national(history)
        slope, intercept = fit_regional(regional_history)
        next_history, next_regional = [], []
        for vote in same_day.vote_id:
            vote = str(vote)
            v = by_vote[vote]
            key = str(v.vote_key.iloc[0])
            y, w = v.yes_share.to_numpy(float), v.weight.to_numpy(float)
            language = v.language.astype(str).to_numpy()
            raw = prior_poll_data(poll_groups.get(key, national.iloc[:0]), date)
            available = raw is not None and w.sum()>0
            region_rows = region_groups.get(key, regional.iloc[:0])
            stamp = str(pd.Timestamp(date).date())
            region_margin = regional_target(region_rows, stamp, 0., "decided") if available else None
            if vote in prediction_groups:
                frame = prediction_groups[vote]
                if not np.array_equal(frame.municipality_id.to_numpy(), v.municipality_id.to_numpy()):
                    raise ValueError("Keys mismatch")
                if not np.allclose(frame.yes_share, y):
                    raise ValueError("Target mismatch")
                p = frame.prediction.to_numpy(float)
                if available != bool(frame.poll_available.iloc[0]):
                    raise ValueError("Availability mismatch")
                forecasts = {}
                for n in NATIONAL:
                    base_p = p.copy()
                    if available and n != "frozen":
                        target = national_target(raw, n, coeff, bias, np.average(p, weights=w))
                        base_p = shift_to(p, w, target)
                    for r in REGIONAL:
                        result = base_p.copy()
                        if r != "none" and region_margin is not None:
                            margins = region_margin
                            if r == "empirical_gap":
                                mass, _ = group_stats(base_p, w, language, LANGUAGES)
                                margins = slope*(region_margin-mass@region_margin) + intercept
                            result = gap_adjust(base_p, w, language, LANGUAGES, margins, 1.)
                        forecasts[n+"__"+r] = result
                # Score only after every prediction for this object is fixed.
                for name, forecast in forecasts.items():
                    d, _ = diagnostics(y, forecast, np.zeros(len(y), dtype=int), 1)
                    records.append({"variant": name, "vote_id": vote, "vote_date": stamp,
                                    "poll_available": available, "regional_available": region_margin is not None,
                                    "mae_pp": d["mae"], "centered_mae": d["centered_mae"]})
                if available:
                    calibration.append({"vote_id": vote, "vote_date": stamp,
                                        "past_national": len(history), "past_regional": len(regional_history),
                                        "intercept": coeff[0], "trend_multiplier": coeff[1],
                                        "undecided_fraction": coeff[2], "bias_shrink": bias,
                                        "region_slope": slope, "regional_intercept": intercept.tolist()})
            # Outcomes are allowed into calibrator history only AFTER all
            # predictions for this date; no voting-date ordering within a day.
            if available:
                next_history.append({**raw, "actual": float(np.average(y, weights=w))})
                if region_margin is not None:
                    mass, actual = group_stats(y, w, language, LANGUAGES)
                    next_regional.append({"poll_gap": region_margin-mass@region_margin,
                                          "actual_gap": actual-mass@actual})
        history.extend(next_history)
        regional_history.extend(next_regional)
    detail = pd.DataFrame(records)
    summary = []
    for name, g in detail.groupby("variant", sort=False):
        if len(g) != 66 or g.vote_date.nunique() != 23:
            raise ValueError("Wrong validation population")
        subset = g[g.regional_available]
        summary.append({"variant": name, "mae": float(g.mae_pp.mean()),
                        "centered_mae": float(g.centered_mae.mean()),
                        "covered_mae": float(subset.mae_pp.mean()),
                        "with_poll_mae": float(g[g.poll_available].mae_pp.mean()),
                        "without_poll_mae": float(g[~g.poll_available].mae_pp.mean()),
                        "interval_vs_v7": [0., 0.] if name == "frozen__none" else paired_date_bootstrap(detail, "frozen__none", name)})
    expected = next(r for r in summary if r["variant"]=="frozen__none")
    if not np.isclose(expected["mae"], 7.547181283176325, atol=.0002, rtol=0):
        raise ValueError("V7 reference changed")
    region_ref = next(r for r in summary if r["variant"]=="frozen__decided_gap")
    if not np.isclose(region_ref["mae"], 7.340163035010155, atol=.0002, rtol=0):
        raise ValueError("V8 regional reference changed")
    output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output / "object_metrics.csv", index=False)
    pd.DataFrame(calibration).to_csv(output / "calibration.csv", index=False)
    pd.DataFrame(summary).to_csv(output / "summary.csv", index=False)
    manifest_out = {"status": "complete", "strict_forecast_ready": False,
                    "same_date_excluded": True, "comparison_targets_loaded": False,
                    "mode": "rolling-origin calibration; prior observed dates only",
                    "inductive_predictions_sha256": checksum, "source_sha256": sha(regional_path),
                    "summary": summary}
    (output / "manifest.json").write_text(json.dumps(manifest_out, indent=2, allow_nan=False), encoding="utf-8")
    print("SUMMARY", json.dumps(summary, allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--regional", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    a = parser.parse_args()
    run(a.base, a.predictions, a.regional, a.output)


if __name__ == "__main__":
    main()

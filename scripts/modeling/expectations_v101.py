"""V10.1 expected national vote-share pilot and multiscale scoring.

The expectation input is a reviewed mean estimated YES percentage, never a
majority probability. Frozen V8.1 profiles and settlement/language corrections
are unchanged. Actual current-date ballot counts enter scoring only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.common.config import ROOT
from scripts.modeling.diagnose_v5_errors import load_outcomes
from scripts.modeling.regional_anchor_v8 import shift_to
from scripts.modeling.semantic_poll_comparison_v4 import paired_date_bootstrap, sha
from scripts.modeling.spatial_margins_v81 import contexts, joint_adjust, observation_system

REFERENCE = 7.229527497606818
POLL_SOURCE = ROOT / "data/external/polls/srg_gfs_polls.csv"
EXPECTATIONS = ROOT / "data/external/expectations_v10/reviewed.csv"
FIXED = {"reference": 0., "expectation25": .25, "expectation50": .5,
         "expectation75": .75, "expectation100": 1.}
VARIANTS = (*FIXED, "walk_forward")


def validate_expectations(reviewed, national):
    required = {"vote_key", "vote_date", "wave", "expected_yes_pp", "source_url", "section"}
    if set(reviewed.columns) != required:
        raise ValueError("Expected exact reviewed mean-share schema")
    if reviewed.duplicated(["vote_key", "wave"]).any():
        raise ValueError("Duplicate expectation")
    if not reviewed.expected_yes_pp.between(0, 100).all():
        raise ValueError("Invalid expected yes percentage")
    if not reviewed.vote_date.between("2016-01-01", "2022-12-31").all():
        raise ValueError("Out-of-scope vote date")
    keys = ["vote_key", "wave", "vote_date", "source_url"]
    joined = reviewed.merge(national[keys + ["published_at", "survey_midpoint"]],
                            on=keys, how="left", validate="one_to_one")
    if joined.published_at.isna().any():
        raise ValueError("Expectation identity not matched to reviewed poll")
    pub = pd.to_datetime(joined.published_at, utc=True)
    vote = pd.to_datetime(joined.vote_date, utc=True)
    if not pub.le(vote - pd.Timedelta(days=1)).all():
        raise ValueError("Publication after forecast cutoff")
    if not pd.to_datetime(joined.survey_midpoint).lt(pd.to_datetime(joined.vote_date)).all():
        raise ValueError("Invalid survey dates")
    return joined.sort_values(["vote_key", "wave"]).drop_duplicates("vote_key", keep="last")


def blend_weight(history):
    """One convex weight, fit on complete earlier voting dates only."""
    if len(history) < 8 or len({r[0] for r in history}) < 3:
        return .5
    a = np.asarray([r[1:] for r in history], dtype=float)
    base, expected, actual = a.T
    delta = expected - base
    # Regularize toward an equal blend (8 pseudo-observations, 8 pp scale).
    penalty = 8 * .08 ** 2
    return float(np.clip((delta @ (actual - base) + .5 * penalty) /
                         (delta @ delta + penalty), 0., 1.))


def apply_expectation(p, w, expected, strength):
    if expected is None or strength == 0.:
        return p.copy()
    if not 0 <= expected <= 1 or not 0 <= strength <= 1:
        raise ValueError("Invalid expectation or weight")
    target = (1 - strength) * np.average(p, weights=w) + strength * expected
    return shift_to(p, w, target)


def multiscale(y, prediction, forecast_weights, actual_yes, actual_no, cantons):
    """Score observed valid ballots, aggregate predictions with ex-ante weights.

    National scope is the admitted municipal population, not necessarily the
    exact official national total (special units may be excluded). Equal weight
    across cantons within an object; equal weight across objects in summaries.
    """
    y, p, w, yes, no = map(lambda x: np.asarray(x, float),
                            (y, prediction, forecast_weights, actual_yes, actual_no))
    if not (len(y) == len(p) == len(w) == len(yes) == len(no) == len(cantons)):
        raise ValueError("Mismatched scoring population")
    if not np.isfinite(np.column_stack([y, p, w, yes, no])).all():
        raise ValueError("Non-finite score inputs")
    if (w < 0).any() or (yes < 0).any() or (no < 0).any() or w.sum() <= 0:
        raise ValueError("Invalid weights or ballots")
    ballots = yes + no
    if (ballots <= 0).any() or not np.allclose(yes / ballots, y, atol=1e-8, rtol=0):
        raise ValueError("Observed shares do not reconcile with counts")
    error = p - y
    observed = float(yes.sum() / ballots.sum())
    national_pred = float(np.average(p, weights=w))
    canton_errors, canton_rows = [], []
    cantons = np.asarray(cantons, dtype=str)
    for canton in np.unique(cantons):
        mask = cantons == canton
        if w[mask].sum() <= 0 or canton in ("", "nan", "None", "<NA>"):
            raise ValueError(f"Cannot aggregate canton {canton} with available weights")
        c_actual = float(yes[mask].sum() / ballots[mask].sum())
        c_pred = float(np.average(p[mask], weights=w[mask]))
        c_error = 100 * abs(c_pred - c_actual)
        canton_errors.append(c_error)
        canton_rows.append({"canton": canton, "observed": c_actual,
                            "prediction": c_pred, "absolute_error_pp": c_error})
    return {
        "mae_pp": float(100 * np.abs(error).mean()),
        "centered_mae_pp": float(100 * np.abs(error - error.mean()).mean()),
        "national_mae_pp": 100 * abs(national_pred - observed),
        "canton_mae_pp": float(np.mean(canton_errors)),
        "national_prediction": national_pred, "national_observed": observed,
        "cantons": len(canton_rows),
    }, canton_rows


def run(base, acquisition, fusion, expectation_path, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve earlier score")
    reviewed = pd.read_csv(expectation_path, dtype={"vote_key": str})
    national = pd.read_csv(POLL_SOURCE, dtype={"vote_key": str})
    approved = validate_expectations(reviewed, national)
    expected = approved.set_index("vote_key").expected_yes_pp.to_dict()
    _, cases = contexts(base, acquisition, fusion)
    # Counts are used only by the scorer and past-date blend calibration.
    outcomes = load_outcomes()
    outcomes = outcomes[outcomes.vote_date.ge("2016-01-01")]
    outcome_groups = {str(k): g.set_index("municipality_id", verify_integrity=True)
                      for k, g in outcomes.groupby("vote_id")}
    history, pending, rows, canton_rows, predictions, calibration = [], [], [], [], [], []
    previous_date = None
    for vote, day, v, f, lm, um in cases:
        if previous_date is not None and day != previous_date:
            if day < previous_date:
                raise ValueError("Cases must be chronological")
            history.extend(pending)
            pending = []
        previous_date = day
        key = str(v.vote_key.iloc[0])
        expectation = expected.get(key)
        expectation = None if expectation is None else float(expectation) / 100
        w = v.weight.to_numpy(float)
        p = f.v8_reference.to_numpy(float)
        a, z, b, i = observation_system(w, v.language.to_numpy(), v.urban.to_numpy(), lm, um)
        current_weights = {**FIXED, "walk_forward": blend_weight(history)}
        # Forecasts fixed BEFORE accessing current outcome counts.
        forecasts = {name: joint_adjust(apply_expectation(p, w, expectation, strength),
                                        w, a, z, b, .1, True, i)
                     for name, strength in current_weights.items()}
        observed = outcome_groups[vote].reindex(v.municipality_id)
        y = v.yes_share.to_numpy(float)
        yes, no = observed.votes_yes.to_numpy(float), observed.votes_no.to_numpy(float)
        canton = observed.canton.astype(str).to_numpy()
        block = v[["vote_id", "municipality_id", "vote_date", "yes_share"]].copy()
        for name, q in forecasts.items():
            m, c = multiscale(y, q, w, yes, no, canton)
            rows.append({"variant": name, "vote_id": vote, "vote_date": str(day.date()),
                         "expectation_available": expectation is not None, **m})
            canton_rows.extend({"variant": name, "vote_id": vote, **r} for r in c)
            block[name] = q
        predictions.append(block)
        if expectation is not None:
            baseline_mean = float(np.average(p, weights=w))
            actual = float(yes.sum() / (yes + no).sum())
            calibration.append({"vote_id": vote, "vote_date": str(day.date()),
                                "expected_yes": expectation, "baseline_national": baseline_mean,
                                "prior_objects": len(history), "prior_dates": len({r[0] for r in history}),
                                "adaptive_weight": current_weights["walk_forward"]})
            pending.append((day, baseline_mean, expectation, actual))
    detail = pd.DataFrame(rows)
    if set(detail.vote_id) != {str(v[0]) for v in cases} or detail.vote_id.nunique() != 66:
        raise ValueError("Wrong scoring population")
    metrics = ["mae_pp", "centered_mae_pp", "national_mae_pp", "canton_mae_pp"]
    summaries = []
    for name, group in detail.groupby("variant", sort=False):
        if len(group) != 66 or group.vote_date.nunique() != 23:
            raise ValueError("Incomplete candidate")
        covered = group[group.expectation_available]
        summary = {"variant": name, "objects": len(group), "covered_objects": len(covered),
                   **{metric: float(group[metric].mean()) for metric in metrics},
                   **{"covered_" + metric: float(covered[metric].mean()) if len(covered) else None
                      for metric in metrics},
                   "gain_interval": [0., 0.] if name == "reference" else
                   paired_date_bootstrap(detail, "reference", name)}
        summaries.append(summary)
    reference = next(r for r in summaries if r["variant"] == "reference")
    if not np.isclose(reference["mae_pp"], REFERENCE, atol=.0002, rtol=0):
        raise ValueError("V8.1 reference did not reproduce")
    output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output / "object_metrics.csv", index=False)
    pd.DataFrame(canton_rows).to_csv(output / "canton_metrics.csv", index=False)
    pd.DataFrame(calibration).to_csv(output / "calibration.csv", index=False)
    pd.DataFrame(summaries).to_csv(output / "summary.csv", index=False)
    pd.concat(predictions, ignore_index=True).to_parquet(output / "predictions.parquet", index=False)
    manifest = {"status": "pilot_complete", "strict_forecast_ready": False,
                "same_date_excluded": True, "comparison_targets_loaded": False,
                "scope": "66 objects, 23 dates, 138868 admitted municipal rows",
                "aggregation": "predicted means use population proxy; observed means use valid ballots only",
                "expectation_source_sha256": sha(expectation_path),
                "prediction_sha256": sha(output / "predictions.parquet"), "summary": summaries}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    print("SUMMARY", json.dumps(summaries, allow_nan=False), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "acquisition", "fusion", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--expectations", type=Path, default=EXPECTATIONS)
    a = p.parse_args()
    run(a.base, a.acquisition, a.fusion, a.expectations, a.output)


if __name__ == "__main__":
    main()

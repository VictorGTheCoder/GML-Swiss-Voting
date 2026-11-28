"""V13.4: historical scoring-only monotone affine L1 contrast diagnostic."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from scripts.modeling.ensemble_v1010 import artifact_root, read_artifact
from scripts.modeling.error_budget_v133 import NAMES, date_interval, offset_diagnosis
from scripts.modeling.semantic_poll_comparison_v4 import sha

EXPECTED_SHA = "622654c965648400469066ac36ee5bb3b886f120d3124f0c786f533275e17089"
METRICS = ["mae_pp", "centered_mae_pp", "median_offset_oracle_pp",
           "affine_oracle_pp", "amplitude_oracle_gain_pp"]


def affine_diagnosis(y, p):
    """Profile out intercept by median, minimize convex L1 over nonnegative slopes.

    No slope, intercept or calibrated municipal prediction leaves this function.
    The prediction range is deliberately unbounded for comparability with V13.3.
    """
    result = offset_diagnosis(y, p)
    y, p = 100 * np.asarray(y, float), 100 * np.asarray(p, float)
    x = p - np.median(p)
    scale = float(np.abs(x).mean())
    target_scale = float(np.abs(y - np.median(y)).mean())
    if scale == 0 or target_scale == 0:
        optimum = target_scale
    else:
        x /= scale

        def loss(slope):
            residual = y - slope * x
            return float(np.abs(residual - np.median(residual)).mean())

        # Centered L1 seminorm triangle inequality: loss(s) >= s - target_scale.
        # The optimum cannot exceed 2*target_scale since loss(0)=target_scale.
        upper = 2 * target_scale
        fit = minimize_scalar(loss, bounds=(0., upper), method="bounded",
                              options={"xatol": 1e-9, "maxiter": 1000})
        if not fit.success:
            raise ValueError("Affine oracle minimization failed")
        # Include both endpoints and the original unit slope to avoid numerical loss.
        optimum = min(float(fit.fun), loss(0.), loss(upper), loss(scale))
    result["affine_oracle_pp"] = optimum
    result["amplitude_oracle_gain_pp"] = result["median_offset_oracle_pp"] - optimum
    if result["amplitude_oracle_gain_pp"] < -1e-8:
        raise ValueError("Affine oracle worse than translation")
    return result


def run(source, prior, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve prior diagnostic")
    root = artifact_root(source)
    if sha(root / "predictions.parquet") != EXPECTED_SHA:
        raise ValueError("Unexpected immutable V11.3 prediction bundle")
    frame = read_artifact(source, ["yes_share", *NAMES]).reset_index()
    prior_files = list(prior.rglob("object_diagnostic.csv"))
    if len(prior_files) != 1:
        raise ValueError("Expected one V13.3 object diagnostic")
    old = pd.read_csv(prior_files[0], dtype={"vote_id": str, "vote_date": str})
    keys = ["variant", "vote_id", "vote_date"]
    if len(old) != 132 or old.duplicated(keys).any():
        raise ValueError("Unexpected prior population")
    rows = []
    for (day, vote), group in frame.groupby(["vote_date", "vote_id"], sort=True):
        for name in NAMES:
            rows.append({"variant": name, "vote_id": vote, "vote_date": str(day.date()),
                         **affine_diagnosis(group.yes_share, group[name])})
    detail = pd.DataFrame(rows)
    cols = ["mae_pp", "centered_mae_pp", "median_offset_oracle_pp"]
    joined = detail.merge(old[keys + cols + ["fold", "domain", "national_mae_pp", "canton_mae_pp"]],
                          on=keys, validate="one_to_one", suffixes=("", "_prior"))
    if len(joined) != len(old) or len(joined) != len(detail):
        raise ValueError("Incomplete scoring join")
    for col in cols:
        if not np.allclose(joined[col], joined[col + "_prior"], rtol=0, atol=1e-8):
            raise ValueError("V13.3 scoring mismatch")
    detail = joined.drop(columns=[col + "_prior" for col in cols])
    summaries = []
    for name, group in detail.groupby("variant", sort=False):
        if len(group) != 66 or group.vote_date.nunique() != 23:
            raise ValueError("Unexpected scoring population")
        scores = group[METRICS + ["national_mae_pp", "canton_mae_pp"]].mean().to_dict()
        if not np.isclose(scores["mae_pp"], NAMES[name], atol=2e-4, rtol=0):
            raise ValueError("Historical baseline mismatch")
        summaries.append({"variant": name, **scores,
                          "affine_interval": date_interval(group, "affine_oracle_pp", seed=134),
                          "amplitude_gain_interval": date_interval(group, "amplitude_oracle_gain_pp", seed=134),
                          "objects_affine_over_4pp": int(group.affine_oracle_pp.gt(4).sum())})
    paired = detail.pivot(index=["vote_date", "vote_id"], columns="variant", values="affine_oracle_pp")
    delta = (paired.reference - paired.institution_text).rename("gain_pp").reset_index()
    output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output / "object_diagnostic.csv", index=False)
    for col in ("fold", "domain"):
        detail.groupby(["variant", col])[METRICS].agg(["mean", "size"]).to_csv(
            output / f"{col}_diagnostic.csv")
    result = {"status": "diagnostic_complete", "oracle_scoring_only": True,
              "prediction_model_changed": False, "objects": 66, "dates": 23, "rows": len(frame),
              "prediction_sha256": EXPECTED_SHA, "prior_diagnostic_sha256": sha(prior_files[0]),
              "summary": summaries, "paired_affine_difference_interval": date_interval(delta, "gain_pp", seed=134)}
    (output / "manifest.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print("SUMMARY", json.dumps(result, allow_nan=False), flush=True)
    print("DOMAIN", detail.groupby(["variant", "domain"])[METRICS].mean().to_json(), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.prior, args.output)


if __name__ == "__main__":
    main()

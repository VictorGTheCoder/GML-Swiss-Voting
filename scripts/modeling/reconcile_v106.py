"""V10.6: hierarchical reconciliation of municipal, canton and national forecasts.

A reduced-dimensional MinT-style GLS system uses one national forecast,
bottom-up canton forecasts and independently fitted canton forecasts. This is
not full 2,110-dimensional MinT: within-canton municipal contrasts are retained.
All error covariance estimates use only earlier out-of-fold voting dates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.modeling.canton_v105 import GEOGRAPHY, aggregate, reference_cantons
from scripts.modeling.expectations_v101 import REFERENCE, multiscale
from scripts.modeling.regional_anchor_v8 import shift_to
from scripts.modeling.semantic_poll_comparison_v4 import paired_date_bootstrap, sha
from scripts.modeling.turnout_v103 import load_ballots

METRICS = ("mae_pp", "centered_mae_pp", "national_mae_pp", "canton_mae_pp")
# Independent canton target, diagonal shrinkage, preserve national level.
CONFIGS = {
    "abs_diag": ("absolute", 1., False),
    "abs_shrink75": ("absolute", .75, False),
    "abs_shrink25": ("absolute", .25, False),
    "center_diag": ("centered", 1., False),
    "center_shrink75": ("centered", .75, False),
    "center_shrink25": ("centered", .25, False),
    "abs_anchor75": ("absolute", .75, True),
    "center_anchor75": ("centered", .75, True),
}


def error_covariance(history, day, n, shrink):
    """Regularized error covariance from prior OOF forecasts, one vector/vote."""
    if not 0 <= shrink <= 1 or n < 1:
        raise ValueError("Invalid reconciliation dimensions")
    # Fixed ex ante scale prior; absolute magnitude matters for small samples.
    prior = np.diag(np.square([.04] + [.065] * n + [.10] * n))
    previous = [error for stamp, error in history if stamp < day]
    if len(previous) < 4:
        return prior, len(previous)
    e = np.asarray(previous, float)
    if e.shape != (len(previous), 1 + 2 * n) or not np.isfinite(e).all():
        raise ValueError("Invalid prior forecast error vectors")
    empirical = np.cov(e, rowvar=False)
    shrunk = (1 - shrink) * empirical + shrink * np.diag(np.diag(empirical))
    cov = (len(e) * shrunk + 8 * prior) / (len(e) + 8)
    return cov, len(e)


def reconcile(anchor, bottom, direct, mass, covariance, fixed_national=False):
    """GLS projection onto coherent canton rates; bounded probability projection.

    S maps canton means to [national, bottom-up cantons, direct cantons].
    The optional equality constraint holds the original national anchor.
    """
    bottom, direct, mass = (np.asarray(x, float) for x in (bottom, direct, mass))
    n = len(bottom)
    if (direct.shape != bottom.shape or mass.shape != bottom.shape
            or not np.isfinite(np.r_[anchor, bottom, direct, mass]).all()
            or (mass <= 0).any() or not 0 <= anchor <= 1):
        raise ValueError("Invalid forecast or canton weights")
    mass = mass / mass.sum()
    s = np.vstack([mass, np.eye(n), np.eye(n)])
    z = np.r_[anchor, bottom, direct]
    cov = np.asarray(covariance, float)
    if cov.shape != (len(z), len(z)) or not np.isfinite(cov).all():
        raise ValueError("Invalid covariance")
    np.linalg.cholesky(cov)
    precision_s = np.linalg.solve(cov, s)
    h = s.T @ precision_s
    rhs = s.T @ np.linalg.solve(cov, z)
    target = np.linalg.solve(h, rhs)
    if fixed_national:
        direction = np.linalg.solve(h, mass)
        target += direction * ((anchor - mass @ target) / (mass @ direction))
        # Clipping can break equality. Bounded projection restores the anchor.
        target = shift_to(target, mass, anchor)
    else:
        target = np.clip(target, 0., 1.)
    return target


def distribute(p, w, canton, labels, target):
    """Exact coherent canton means while retaining local contrasts up to clipping."""
    q = p.copy()
    for c, value in zip(labels, target, strict=True):
        mask = canton == c
        q[mask] = shift_to(p[mask], w[mask], value)
    if not np.allclose(aggregate(q, w, canton, labels), target, atol=1e-9, rtol=0):
        raise ValueError("Reconciliation failed")
    return q


def run(source, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve earlier experiments")
    m = json.loads((source / "manifest.json").read_text())
    pp, cp = source / "predictions.parquet", source / "direct_canton_predictions.csv"
    if m["status"] != "complete" or m["prediction_sha256"] != sha(pp) or m["direct_canton_sha256"] != sha(cp):
        raise ValueError("Frozen V10.5 artifact mismatch")
    if m["geography_sha256"] != sha(GEOGRAPHY):
        raise ValueError("Reference geography changed")
    cols = ["vote_id", "municipality_id", "vote_date", "reference",
            "reference_weight", "pooled_weights_control_weight"]
    predictions = pd.read_parquet(pp, columns=cols)
    for key in ("vote_id", "municipality_id"):
        predictions[key] = predictions[key].astype(str)
    predictions["vote_date"] = pd.to_datetime(predictions.vote_date)
    if len(predictions) != 138868 or predictions.vote_id.nunique() != 66 or predictions.vote_date.nunique() != 23:
        raise ValueError("Frozen population mismatch")
    if predictions.vote_date.ge("2023-01-01").any() or predictions.duplicated(["vote_id", "municipality_id"]).any():
        raise ValueError("Invalid evaluation keys")
    # Do not read the observed column of the canton artifact as a model input.
    direct = pd.read_csv(cp, dtype={"vote_id": str}, usecols=[
        "vote_id", "vote_date", "canton", "weight", "bottom_up", "absolute", "centered", "national_anchor",
    ])
    direct["vote_date"] = pd.to_datetime(direct.vote_date)
    if direct.duplicated(["vote_id", "canton"]).any():
        raise ValueError("Duplicate canton predictions")
    by_vote = {k: g.set_index("canton", verify_integrity=True) for k, g in direct.groupby("vote_id")}
    geography = pd.read_parquet(GEOGRAPHY, columns=["municipality_id", "canton"])
    labels = np.array(sorted(geography.canton.astype(str).str.upper().unique()))
    outcomes = load_ballots()
    observed = {k: g.set_index("municipality_id", verify_integrity=True) for k, g in outcomes.groupby("vote_id")}
    histories = {"absolute": [], "centered": []}
    records, canton_rows, blocks = [], [], []
    for day, cases in predictions.groupby("vote_date", sort=True):
        pending = {"absolute": [], "centered": []}
        for vote, v in cases.groupby("vote_id", sort=False):
            v = v.sort_values("municipality_id")
            ids = v.municipality_id.to_numpy()
            p = v.reference.to_numpy(float)
            w = v.reference_weight.to_numpy(float)
            pooled = v.pooled_weights_control_weight.to_numpy(float)
            canton = reference_cantons(geography, ids)
            if not np.array_equal(np.unique(canton), labels):
                raise ValueError("Expected a complete fixed canton universe")
            d = by_vote[vote].reindex(labels)
            if not d.vote_date.eq(day).all():
                raise ValueError("Canton source date mismatch")
            mass = np.array([pooled[canton == c].sum() for c in labels])
            anchor = float(np.average(p, weights=pooled))
            bottom = aggregate(p, pooled, canton, labels)
            if (not np.allclose(mass, d.weight) or not np.allclose(bottom, d.bottom_up)
                    or not np.allclose(anchor, d.national_anchor)):
                raise ValueError("Bottom-up artifact inconsistent")
            estimates = {name: d[name].to_numpy(float) for name in histories}
            forecasts = {"reference": (p, w), "pooled_control": (p, pooled)}
            prior_counts = {}
            for name, (kind, shrink, fixed) in CONFIGS.items():
                cov, count = error_covariance(histories[kind], day, len(labels), shrink)
                target = reconcile(anchor, bottom, estimates[kind], mass, cov, fixed)
                q = distribute(p, pooled, canton, labels, target)
                if fixed and not np.isclose(np.average(q, weights=pooled), anchor, atol=1e-9):
                    raise ValueError("National anchor changed")
                forecasts[name] = (q, pooled)
                prior_counts[name] = count
            # Observed target counts are accessed only after all forecasts fixed.
            actual = observed[vote].reindex(ids)
            yes = actual.votes_yes.to_numpy(float)
            no = actual.votes_no.to_numpy(float)
            valid = yes + no
            y = yes / valid
            if not np.array_equal(actual.canton.astype(str).to_numpy(), canton):
                raise ValueError("Observed geography mismatch")
            national = yes.sum() / valid.sum()
            obs = aggregate(y, valid, canton, labels)
            for kind in histories:
                pending[kind].append((day, np.r_[anchor - national, bottom - obs, estimates[kind] - obs]))
            block = v[["vote_id", "municipality_id", "vote_date"]].copy()
            block["yes_share"] = y
            fold = "2016-18" if day.year <= 2018 else "2019-20" if day.year <= 2020 else "2021-22"
            for name, (q, weights) in forecasts.items():
                metrics, cs = multiscale(y, q, weights, yes, no, canton)
                common, _ = multiscale(y, q, w, yes, no, canton)
                records.append({"variant": name, "vote_id": vote, "vote_date": str(day.date()),
                                "fold": fold, "prior_covariance_objects": prior_counts.get(name, 0), **metrics,
                                "common_national_mae_pp": common["national_mae_pp"],
                                "common_canton_mae_pp": common["canton_mae_pp"]})
                canton_rows.extend({"variant": name, "vote_id": vote, **c} for c in cs)
                block[name] = q
                block[name + "_weight"] = weights
            blocks.append(block)
        # Only finished dates update the covariance history.
        for kind in histories:
            histories[kind].extend(pending[kind])
    detail = pd.DataFrame(records)
    extra = ["common_national_mae_pp", "common_canton_mae_pp"]
    summary = []
    for name, g in detail.groupby("variant", sort=False):
        if len(g) != 66 or g.vote_date.nunique() != 23:
            raise ValueError("Incomplete benchmark")
        summary.append({"variant": name, "objects": len(g),
                        **{c: float(g[c].mean()) for c in [*METRICS, *extra]},
                        "gain_interval": [0., 0.] if name == "reference" else
                        paired_date_bootstrap(detail, "reference", name)})
    if not np.isclose(summary[0]["mae_pp"], REFERENCE, atol=.0002, rtol=0):
        raise ValueError("V8.1 reference changed")
    output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output / "object_metrics.csv", index=False)
    detail.groupby(["variant", "fold"])[list(METRICS) + extra].mean().to_csv(output / "fold_metrics.csv")
    pd.DataFrame(canton_rows).to_csv(output / "canton_metrics.csv", index=False)
    pd.DataFrame(summary).to_csv(output / "summary.csv", index=False)
    pd.concat(blocks, ignore_index=True).to_parquet(output / "predictions.parquet", index=False)
    result = {"status": "complete", "strict_forecast_ready": False, "comparison_targets_loaded": False,
              "same_date_excluded": True, "configs": CONFIGS, "source_manifest_sha256": sha(source / "manifest.json"),
              "prediction_sha256": sha(output / "predictions.parquet"), "summary": summary,
              "method": "reduced MinT-style reconciliation at canton resolution, not full municipal MinT"}
    (output / "manifest.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print("SUMMARY", json.dumps(summary, allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)


if __name__ == "__main__":
    main()

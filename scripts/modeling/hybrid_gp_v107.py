"""V10.7: separable object x geography Gaussian residual profiles.

Learn from strictly earlier out-of-fold errors of the frozen V8.1 reference.
The spatial covariance is built from pre-2016 historical voting contrasts
and fixed retrospective OFS geography. No target-date outcomes as inputs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics.pairwise import euclidean_distances
from sklearn.utils.extmath import randomized_svd

from scripts.modeling.canton_v105 import CATS, GEOGRAPHY, NUMS, reference_cantons
from scripts.modeling.expectations_v101 import REFERENCE, multiscale
from scripts.modeling.regional_anchor_v8 import shift_to
from scripts.modeling.semantic_poll_comparison_v4 import paired_date_bootstrap, sha
from scripts.modeling.spatial_margins_v81 import contexts
from scripts.modeling.turnout_v103 import load_ballots

METRICS = ("mae_pp", "centered_mae_pp", "national_mae_pp", "canton_mae_pp")
CONFIGS = {
    "mean_identity": ("constant", "identity", 1., .5),
    "object_identity": ("mixed", "identity", 1., .5),
    "object_latent": ("mixed", "latent", 1., .5),
    "object_geo": ("mixed", "geography", 1., .5),
    "object_hybrid": ("mixed", "hybrid", 1., .5),
    "object_hybrid_strong": ("mixed", "hybrid", 4., .5),
    "object_hybrid_full": ("mixed", "hybrid", 1., 1.),
}
MIN_HISTORY = 8


def object_features(row):
    f = {name + "=" + str(row.get(name, "unknown")): 1. for name in CATS}
    for name in NUMS:
        value = row.get(name, np.nan)
        if pd.notna(value) and np.isfinite(float(value)):
            f[name] = float(value)
        else:
            f[name + "_missing"] = 1.
    return f


def object_kernel(prior, query, kind):
    if kind == "constant":
        return np.ones((len(prior), len(prior))), np.ones(len(prior))
    vectorizer = DictVectorizer(sparse=False)
    x = vectorizer.fit_transform(prior)
    q = vectorizer.transform([query])
    scale = max(float(np.square(x).sum(axis=1).mean()), 1e-9)
    d = euclidean_distances(x, squared=True)
    pos = d[np.triu_indices(len(x), 1)]
    pos = pos[pos > 1e-9]
    width = float(np.median(pos)) if len(pos) else 1.
    # Constant term retains global historical mean residual; PSD sum.
    k = .2 + .4 * (x @ x.T / scale) + .4 * np.exp(-d / width)
    cross = .2 + .4 * (q @ x.T / scale) + .4 * np.exp(-euclidean_distances(q, x, squared=True) / width)
    return k, cross.ravel()


def spectral_factor(features):
    """K_geo = I + U diag(s) U.T; average nonzero added eigenvalue one."""
    x = np.asarray(features, float)
    x = x - x.mean(axis=0)
    norm = np.linalg.norm(x, axis=0)
    x = x[:, norm > 1e-10] / norm[norm > 1e-10]
    if not x.shape[1]:
        return np.empty((len(x), 0)), np.empty(0)
    u, s, _ = np.linalg.svd(x, full_matrices=False)
    keep = s > 1e-8
    s = np.square(s[keep])
    return u[:, keep], s / s.mean()


def spatial_factors(outcomes, geography, ids):
    """Fixed historical basis, no outcome in or after the benchmark."""
    h = outcomes[outcomes.vote_date.lt("2016-01-01")].copy()
    h["share"] = h.votes_yes / (h.votes_yes + h.votes_no)
    mat = h.pivot(index="vote_id", columns="municipality_id", values="share").reindex(columns=ids)
    r = mat.to_numpy(float)
    centered = r - np.nanmean(r, axis=1, keepdims=True)
    centered = np.nan_to_num(centered)
    centered -= centered.mean(axis=0)
    _, s, v = randomized_svd(centered, n_components=20, random_state=20261124, n_iter=5)
    latent = v.T * s
    g = geography.set_index("municipality_id").reindex(ids)
    if g[["canton", "language_region", "urban_rural"]].isna().any().any():
        raise ValueError("Missing OFS geography")
    explicit = pd.get_dummies(g[["canton", "language_region", "urban_rural"]].astype(str)).to_numpy(float)
    return {
        "identity": (np.empty((len(ids), 0)), np.empty(0)),
        "latent": spectral_factor(latent),
        "geography": spectral_factor(explicit),
        "hybrid": spectral_factor(np.column_stack([latent, explicit])),
    }, len(mat)


def posterior(k, cross, residual, factor, noise):
    """Exact separable GP mean on a rectangular, zero-filled residual grid.

    In the complement of the low-rank geographical basis K_geo=I.
    In mode j, K_geo has eigenvalue 1+s_j; noise becomes noise/(1+s_j).
    """
    u, s = factor
    if noise <= 0 or k.shape != (len(residual), len(residual)):
        raise ValueError("Invalid covariance")
    identity = np.eye(len(k))
    mean = cross @ np.linalg.solve(k + noise * identity, residual)
    if len(s):
        coeff = residual @ u
        base = mean @ u
        adjusted = np.array([
            cross @ np.linalg.solve(k + noise / (1 + ev) * identity, coeff[:, j])
            for j, ev in enumerate(s)
        ])
        mean += (adjusted - base) @ u.T
    return mean


def correction(history, day, features, factors, kind, spatial, noise):
    prior = [r for r in history if r[0] < day]
    n = len(prior)
    if n < MIN_HISTORY or len({r[0] for r in prior}) < 3:
        return np.zeros(len(factors["identity"][0])), n
    k, cross = object_kernel([r[1] for r in prior], features, kind)
    r = np.stack([row[2] for row in prior])
    return posterior(k, cross, r, factors[spatial], noise), n


def run(base, acquisition, fusion, frozen, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve previous experiments")
    manifest = json.loads((frozen / "manifest.json").read_text())
    source = frozen / "predictions.parquet"
    if manifest["status"] != "complete" or manifest["prediction_sha256"] != sha(source):
        raise ValueError("Frozen predictions changed")
    if manifest["geography_sha256"] != sha(GEOGRAPHY):
        raise ValueError("Geography changed")
    pred = pd.read_parquet(source, columns=[
        "vote_id", "municipality_id", "vote_date", "reference", "reference_weight",
    ])
    for key in ("vote_id", "municipality_id"):
        pred[key] = pred[key].astype(str)
    if len(pred) != 138868 or pred.vote_id.nunique() != 66 or pred.vote_date.ge("2023-01-01").any():
        raise ValueError("Incorrect evaluation population")
    pg = {k: g.set_index("municipality_id", verify_integrity=True) for k, g in pred.groupby("vote_id")}
    data, cases = contexts(base, acquisition, fusion)
    fields = [x for x in (*CATS, *NUMS) if x in data]
    meta = data[["vote_id", *fields]].drop_duplicates()
    if meta.vote_id.duplicated().any():
        raise ValueError("Nonconstant object features")
    metadata = meta.set_index("vote_id")
    geo = pd.read_parquet(GEOGRAPHY, columns=["municipality_id", "canton", "language_region", "urban_rural"])
    geo["municipality_id"] = geo.municipality_id.astype(str)
    grid = pd.Index(sorted(geo.municipality_id.unique()))
    outcomes = load_ballots()
    factors, historical_objects = spatial_factors(outcomes, geo, grid)
    observed = {k: g.set_index("municipality_id", verify_integrity=True)
                for k, g in outcomes.groupby("vote_id")}
    history, detail, canton_rows, blocks = [], [], [], []
    for vote, day, v, _, _, _ in cases:
        ids = v.municipality_id.to_numpy()
        pos = grid.get_indexer(ids)
        if (pos < 0).any():
            raise ValueError("Unknown geography")
        f = pg[vote].reindex(ids)
        if not pd.to_datetime(f.vote_date).eq(day).all():
            raise ValueError("Forecast date mismatch")
        p, w = f.reference.to_numpy(float), f.reference_weight.to_numpy(float)
        features = object_features(metadata.loc[vote].to_dict())
        canton = reference_cantons(geo, ids)
        forecasts = {"reference": p}
        cache = {}
        n = 0
        for name, (kind, spatial, noise, strength) in CONFIGS.items():
            key = (kind, spatial, noise)
            if key not in cache:
                cache[key], n = correction(history, day, features, factors, *key)
            delta = cache[key][pos]
            forecasts[name] = shift_to(p + strength * delta, w, np.average(p, weights=w))
        # Only after all predictions are fixed: read observed counts.
        actual = observed[vote].reindex(ids)
        yes, no = actual.votes_yes.to_numpy(float), actual.votes_no.to_numpy(float)
        y = yes / (yes + no)
        if not np.array_equal(canton, actual.canton.astype(str).to_numpy()) or not np.allclose(y, v.yes_share):
            raise ValueError("Scoring population mismatch")
        error = y - p
        r = np.zeros(len(grid))
        r[pos] = error - error.mean()
        # Strict day filter in correction excludes all same-day records.
        history.append((day, features, r))
        block = v[["vote_id", "municipality_id", "vote_date", "yes_share"]].copy()
        fold = "2016-18" if day.year <= 2018 else "2019-20" if day.year <= 2020 else "2021-22"
        for name, q in forecasts.items():
            m, c = multiscale(y, q, w, yes, no, canton)
            detail.append({"variant": name, "vote_id": vote, "vote_date": str(day.date()),
                           "fold": fold, "prior_objects": n, "active": n >= MIN_HISTORY and
                           len({row[0] for row in history if row[0] < day}) >= 3, **m})
            canton_rows.extend({"variant": name, "vote_id": vote, **x} for x in c)
            block[name] = q
            block[name + "_weight"] = w
        blocks.append(block)
    detail = pd.DataFrame(detail)
    summary = []
    for name, g in detail.groupby("variant", sort=False):
        if len(g) != 66 or g.vote_date.nunique() != 23:
            raise ValueError("Incomplete validation")
        summary.append({"variant": name, "objects": len(g), "covered_objects": int(g.active.sum()),
                        **{m: float(g[m].mean()) for m in METRICS},
                        "covered_mae_pp": float(g.loc[g.active, "mae_pp"].mean()),
                        "gain_interval": [0., 0.] if name == "reference" else
                        paired_date_bootstrap(detail, "reference", name)})
    if not np.isclose(summary[0]["mae_pp"], REFERENCE, atol=.0002, rtol=0):
        raise ValueError("Reference changed")
    output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output / "object_metrics.csv", index=False)
    detail.groupby(["variant", "fold"])[list(METRICS)].mean().to_csv(output / "fold_metrics.csv")
    pd.DataFrame(canton_rows).to_csv(output / "canton_metrics.csv", index=False)
    pd.DataFrame(summary).to_csv(output / "summary.csv", index=False)
    pd.concat(blocks, ignore_index=True).to_parquet(output / "predictions.parquet", index=False)
    result = {"status": "complete", "strict_forecast_ready": False, "comparison_targets_loaded": False,
              "same_date_excluded": True, "configs": CONFIGS, "object_fields": fields,
              "geography_sha256": sha(GEOGRAPHY), "historical_basis_objects": historical_objects,
              "source_prediction_sha256": sha(source), "prediction_sha256": sha(output / "predictions.parquet"),
              "summary": summary}
    (output / "manifest.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    print("SUMMARY", json.dumps(summary, allow_nan=False), flush=True)
    print("HISTORICAL_BASIS_OBJECTS", historical_objects, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "acquisition", "fusion", "frozen", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    run(a.base, a.acquisition, a.fusion, a.frozen, a.output)


if __name__ == "__main__":
    main()

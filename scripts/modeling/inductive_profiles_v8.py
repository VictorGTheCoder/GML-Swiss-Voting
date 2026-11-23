"""V8 inductive matrix factorization of municipal voting contrasts.

All estimators are trained on objects strictly before the evaluation window.
Use the unchanged V3 global level predictor and poll anchor to isolate local
shape prediction. Compare unsupervised PCA/XGBoost against kernel-based
multi-output regression and supervised reduced-rank factorization. Nested
selection sees only an inner chronological holdout from the outer train.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from scipy.linalg import eigh
from sklearn.metrics.pairwise import euclidean_distances
from sklearn.utils.extmath import randomized_svd
from threadpoolctl import threadpool_limits

from scripts.modeling.audit_xgboost_capacity import (
    anchor_fast,
    diagnostics,
    poll_context,
    prepare_fold,
    reconstruct,
)
from scripts.modeling.local_profiles_v7 import fit_heads, historical_matrix, metric_basis
from scripts.modeling.object_profile_v2 import ObjectProfileRegressor
from scripts.modeling.semantic_poll_comparison_v4 import V3_PLAN, paired_date_bootstrap, sha
from scripts.modeling.semantic_training_v5 import (
    CURRENT_POLLS,
    EXTRAS,
    HISTORICAL,
    HISTORICAL_POLLS,
    PLAN,
    V4,
    check_plan,
    prepare_data,
)
from scripts.modeling.temporal_drift_v6 import recency_weights

# Deliberately compact grid; nested selection never uses an outer outcome.
# kernel, lambda, supervised rank (0 = unrestricted), missing-cell EM updates.
CANDIDATES = {
    "linear_full_003": ("linear", .03, 0, 0),
    "linear_full_03": ("linear", .3, 0, 0),
    "linear_full_3": ("linear", 3., 0, 0),
    "rbf_full_003": ("rbf", .03, 0, 0),
    "rbf_full_03": ("rbf", .3, 0, 0),
    "rbf_full_3": ("rbf", 3., 0, 0),
    "linear_rank5": ("linear", .3, 5, 0),
    "linear_rank10": ("linear", .3, 10, 0),
    "linear_rank20": ("linear", .3, 20, 0),
    "rbf_rank5": ("rbf", .3, 5, 0),
    "rbf_rank10": ("rbf", .3, 10, 0),
    "rbf_rank20": ("rbf", .3, 20, 0),
    "mixed_rank10": ("mixed", .3, 10, 0),
    "masked_linear_rank10": ("linear", .3, 10, 3),
    "masked_rbf_rank10": ("rbf", .3, 10, 3),
}
BASELINES = ("reference", "pca_recent5")


class KernelGeometry:
    """Positive-semidefinite centered kernels using TRAIN statistics only."""

    def __init__(self, train, query, kind):
        x, z = np.asarray(train, float), np.asarray(query, float)
        if x.ndim != 2 or z.ndim != 2 or x.shape[1] != z.shape[1]:
            raise ValueError("Mismatched object features")
        if not np.isfinite(x).all() or not np.isfinite(z).all():
            raise ValueError("Non-finite preprocessed inputs")
        # Linear component normalized by the train average squared row norm.
        scale = max(float(np.square(x).sum(axis=1).mean()), 1e-12)
        linear = x @ x.T / scale
        cross_linear = z @ x.T / scale
        if kind == "linear":
            k, cross = linear, cross_linear
        else:
            d = euclidean_distances(x, squared=True)
            positive = d[np.triu_indices(len(x), 1)]
            positive = positive[positive > 1e-12]
            bandwidth = float(np.median(positive)) if len(positive) else 1.
            rbf = np.exp(-d / bandwidth)
            cross_rbf = np.exp(-euclidean_distances(z, x, squared=True) / bandwidth)
            if kind == "rbf":
                k, cross = rbf, cross_rbf
            elif kind == "mixed":
                k, cross = .5 * (linear + rbf), .5 * (cross_linear + cross_rbf)
            else:
                raise ValueError("Unknown kernel")
        train_col = k.mean(axis=0)
        grand = float(k.mean())
        k = k - train_col[None, :] - k.mean(axis=1)[:, None] + grand
        cross = cross - train_col[None, :] - cross.mean(axis=1)[:, None] + grand
        k = (k + k.T) / 2
        # Scale regularization comparably across different kernel families.
        scale = max(float(np.trace(k) / len(k)), 1e-12)
        self.k = k / scale
        self.cross = cross / scale
        eig, u = eigh(self.k)
        self.eig = np.clip(eig, 0, None)
        self.u = u


def inductive_profile(geometry, residual, regularization, rank, em_steps=0):
    """Penalized supervised rank constraint; optional masked completion.

    Minimize ||R - K A||_F^2 + lambda tr(A^T K A), constrained to rank d.
    The supervised output basis is obtained from the SVD of
    diag(sqrt(eig/(eig+lambda))) U^T R. Unlike unsupervised PCA, this basis
    is optimized for the part of municipal variation predictable from X.
    Missing training cells may be refined by alternating fitted values, but
    never read from validation. Prediction uses K(query, train) only.
    """
    if regularization <= 0 or rank < 0 or em_steps < 0:
        raise ValueError("Invalid inductive configuration")
    r = np.asarray(residual, float)
    observed = np.isfinite(r)
    completed = np.where(observed, r, 0.)
    e, u = geometry.eig, geometry.u
    for step in range(em_steps + 1):
        center = completed.mean(axis=0)
        y = completed - center
        rotated = u.T @ y
        if rank:
            supervised = np.sqrt(e / (e + regularization))[:, None] * rotated
            _, _, basis = randomized_svd(
                supervised, n_components=min(rank, min(supervised.shape)),
                random_state=20261123, n_iter=5,
            )
            alpha = u @ ((rotated @ basis.T) / (e + regularization)[:, None])
            if step < em_steps:
                fitted = center + (geometry.k @ alpha) @ basis
            else:
                query = center + (geometry.cross @ alpha) @ basis
        else:
            alpha = u @ (rotated / (e + regularization)[:, None])
            if step < em_steps:
                fitted = center + geometry.k @ alpha
            else:
                query = center + geometry.cross @ alpha
        if step < em_steps:
            completed = np.where(observed, r, fitted)
    # A profile must represent contrasts, not change the mean-level head.
    return query - query.mean(axis=1, keepdims=True)


def predict_from_profile(global_head, profiles, fold):
    value = global_head[fold["val_idx"]].astype(float).copy()
    known = fold["val_muni"] >= 0
    value[known] += profiles[fold["val_idx"][known], fold["val_muni"][known]]
    return np.clip(value, 0, 1)


def profile_centered_mae(profile, fold):
    """Inner selection metric: only contrast error, no national poll or level."""
    residual_prediction = np.zeros(len(fold["val_y"]))
    known = fold["val_muni"] >= 0
    residual_prediction[known] = profile[fold["val_idx"][known], fold["val_muni"][known]]
    metrics, _ = diagnostics(
        fold["val_y"], residual_prediction, fold["val_idx"], len(fold["val_ids"])
    )
    return metrics["centered_mae"]


def make_candidate_profiles(fold, residuals):
    geometry = {}
    for name, (kind, lam, rank, em) in CANDIDATES.items():
        if kind not in geometry:
            geometry[kind] = KernelGeometry(fold["train_x"], fold["val_x"], kind)
        yield name, inductive_profile(geometry[kind], residuals, lam, rank, em)


def choose_inner(train, numeric, categorical, params, outer_cutoff):
    """Two consecutive inner blocks, all dates earlier than outer validation."""
    cutoff = pd.Timestamp(outer_cutoff)
    scores = {name: [] for name in CANDIDATES}
    for start, end in [(cutoff - pd.DateOffset(years=8), cutoff - pd.DateOffset(years=4)),
                       (cutoff - pd.DateOffset(years=4), cutoff)]:
        a = train[train.vote_date.lt(start)]
        b = train[train.vote_date.ge(start) & train.vote_date.lt(end)]
        if a.empty or b.empty or a.vote_date.max() >= b.vote_date.min() or b.vote_date.max() >= cutoff:
            raise ValueError("Inner temporal split invalid")
        fold = prepare_fold(a, b, numeric, categorical, params)
        _, _, residuals = historical_matrix(a, fold["train_ids"])
        for name, profile in make_candidate_profiles(fold, residuals):
            scores[name].append((profile_centered_mae(profile, fold), len(fold["val_ids"])))
    pooled = {name: float(np.average([x[0] for x in pairs], weights=[x[1] for x in pairs]))
              for name, pairs in scores.items()}
    return min(pooled, key=pooled.get), pooled


def run(base, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Do not overwrite a benchmark")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    check_plan(plan, json.loads(V3_PLAN.read_text(encoding="utf-8")))
    data, _, numeric, categorical, _ = prepare_data(
        base, EXTRAS, HISTORICAL, V4, CURRENT_POLLS, HISTORICAL_POLLS, plan
    )
    params = dict(plan["regressor_parameters"])
    output.mkdir(parents=True, exist_ok=True)
    rows, objects, selections = [], [], []
    retained = {name: [] for name in (*BASELINES, "nested_inductive")}
    for window in plan["validation_windows"]:
        train = data[data.vote_date.lt(window["start"])]
        evaluation = data[data.vote_date.between(window["start"], window["end"])]
        if train.empty or evaluation.empty or train.vote_date.max() >= evaluation.vote_date.min():
            raise ValueError("Invalid chronology")
        with threadpool_limits(limits=2):
            selected, inner_scores = choose_inner(train, numeric, categorical, params, window["start"])
            fold = prepare_fold(train, evaluation, numeric, categorical, params)
            munis, mu, residuals = historical_matrix(train, fold["train_ids"])
            proto = ObjectProfileRegressor(numeric, categorical, **params)
            original = fit_heads(proto, fold["train_x"], fold["heads"], fold["val_x"])
            reference = reconstruct(original, fold["pca"], fold["val_idx"], fold["val_muni"])
            date_lookup = train[["vote_id", "vote_date"]].drop_duplicates().set_index("vote_id").vote_date
            weights = recency_weights(date_lookup.loc[fold["train_ids"]], window["start"], 5)
            basis, heads = metric_basis(
                residuals, mu, weights, np.ones(len(munis)), params["dimensions"], params["random_state"]
            )
            recent = original.copy()
            recent[:, 1:] = fit_heads(proto, fold["train_x"], heads[:, 1:], fold["val_x"])
            recent_pred = reconstruct(recent, basis, fold["val_idx"], fold["val_muni"])
            candidates = {"reference": reference, "pca_recent5": recent_pred}
            for name, profile in make_candidate_profiles(fold, residuals):
                candidates[name] = predict_from_profile(original[:, 0], profile, fold)
            candidates["nested_inductive"] = candidates[selected].copy()
        _, groups = poll_context(train, evaluation, plan["frozen_poll_parameters"])
        lookup = evaluation[["vote_id", "vote_date", "poll_available"]].drop_duplicates().set_index("vote_id")
        for name, predicted in candidates.items():
            adjusted = anchor_fast(predicted, groups)
            nv = len(fold["val_ids"])
            st, _ = diagnostics(fold["val_y"], predicted, fold["val_idx"], nv)
            po, per = diagnostics(fold["val_y"], adjusted, fold["val_idx"], nv)
            row = {"configuration": name, "window": window["name"], "validation_objects": nv,
                   **{"structural_" + k: v for k, v in st.items()},
                   **{"anchored_" + k: v for k, v in po.items()}}
            rows.append(row)
            for vote, mae in zip(fold["val_ids"], per, strict=True):
                objects.append({"variant": name, "vote_id": vote,
                                "vote_date": str(lookup.loc[vote, "vote_date"].date()),
                                "poll_available": int(lookup.loc[vote, "poll_available"]),
                                "mae_pp": float(mae)})
            if name in retained:
                frame = evaluation[["vote_id", "municipality_id", "vote_date", "yes_share", "poll_available"]].copy()
                frame["structural_prediction"] = predicted
                frame["prediction"] = adjusted
                frame["window"] = window["name"]
                retained[name].append(frame)
        selections.append({"window": window["name"], "chosen": selected, "inner_centered_mae": inner_scores})
        print("INNER", json.dumps(selections[-1]), flush=True)
    detail, object_table = pd.DataFrame(rows), pd.DataFrame(objects)
    summary = []
    for name, group in detail.groupby("configuration", sort=False):
        row = {"configuration": name}
        for col in detail:
            if col.startswith(("structural_", "anchored_")):
                row[col] = float(np.average(group[col], weights=group.validation_objects))
        subset = object_table[object_table.variant.eq(name)]
        if len(subset) != 66 or subset.vote_id.nunique() != 66 or subset.vote_date.nunique() != 23:
            raise ValueError("Wrong validation population")
        row["with_poll_mae"] = float(subset[subset.poll_available.eq(1)].mae_pp.mean())
        row["without_poll_mae"] = float(subset[subset.poll_available.eq(0)].mae_pp.mean())
        if name != "reference":
            row["gain_interval"] = paired_date_bootstrap(object_table, "reference", name)
        summary.append(row)
    reference = next(r for r in summary if r["configuration"] == "reference")
    recent = next(r for r in summary if r["configuration"] == "pca_recent5")
    if not np.isclose(reference["anchored_mae"], 7.618292700184025, atol=.0002, rtol=0):
        raise ValueError("V3 reference changed")
    if not np.isclose(recent["anchored_mae"], 7.547181283176325, atol=.0002, rtol=0):
        raise ValueError("V7 recent-PCA reference changed")
    detail.to_csv(output / "fold_metrics.csv", index=False)
    object_table.to_csv(output / "object_metrics.csv", index=False)
    pd.DataFrame(summary).to_csv(output / "summary.csv", index=False)
    hashes = {}
    for name, blocks in retained.items():
        path = output / f"{name}_predictions.parquet"
        pd.concat(blocks, ignore_index=True).to_parquet(path, index=False)
        hashes[name] = sha(path)
    manifest = {"status": "complete", "strict_forecast_ready": False,
                "comparison_targets_loaded": False, "same_population": True,
                "plan": plan, "configurations": CANDIDATES, "inner_selection": selections,
                "prepared_sha256": sha(base / "dataset.parquet"), "prediction_hashes": hashes,
                "summary": summary}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    print("SUMMARY", json.dumps(summary, allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run(args.base, args.output)


if __name__ == "__main__":
    main()

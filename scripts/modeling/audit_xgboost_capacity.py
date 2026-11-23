"""Capacity audit of the frozen V3 and V5 object-profile regressors.

Only development dates through 2022 are scored; no candidate is promoted.
Fit one train-only PCA and preprocessing per feature set/fold, then train
each XGBoost head once to the maximum tree budget and inspect checkpoints.
Training MAE is structural, never artificially anchored to historical polls.
Validation is reported both structurally and with the frozen V3 poll anchor.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from threadpoolctl import threadpool_limits

from scripts.modeling.object_profile_v2 import ObjectProfileRegressor
from scripts.modeling.poll_anchor import PollAnchoredRegressor
from scripts.modeling.semantic_poll_comparison_v4 import V3_PLAN, sha
from scripts.modeling.semantic_training_v5 import (
    CURRENT_POLLS,
    EXTRAS,
    HISTORICAL,
    HISTORICAL_POLLS,
    PLAN,
    V4,
    check_plan,
    fold_features,
    prepare_data,
)

# Declared before running: a capacity sweep, then one-at-a-time changes to
# regularization, leaf support and learning rate. No adaptive tuning.
STEPS = (30, 75, 150, 300, 600)
GRID = {
    "depth_1": {"max_depth": 1},
    "depth_2": {"max_depth": 2},
    "depth_3": {"max_depth": 3},
    "depth_4": {"max_depth": 4},
    "depth_6": {"max_depth": 6},
    "depth_9": {"max_depth": 9},
    "l2_1": {"max_depth": 6, "reg_lambda": 1.0},
    "l2_100": {"max_depth": 6, "reg_lambda": 100.0},
    "child_5": {"max_depth": 6, "model_params": {"min_child_weight": 5}},
    "child_15": {"max_depth": 6, "model_params": {"min_child_weight": 15}},
    "lr_001": {"max_depth": 6, "learning_rate": 0.01},
    "lr_010": {"max_depth": 6, "learning_rate": 0.1},
}
FEATURE_SETS = {"v3": "baseline_pca5", "v5": "baseline_coarse_mechanisms"}


class ArrayPredictor:
    """Provide already-computed predictions to the original poll adapter."""

    def __init__(self, values):
        self.values = values

    def predict(self, frame):
        if len(frame) != len(self.values):
            raise ValueError("Anchor row count changed")
        return self.values


def poll_context(train, evaluation, params):
    """Use the original anchor to determine admissibility and poll targets.

    Weight=1 makes the target independent of the structural predictions.
    The same offset bisection is subsequently applied for each checkpoint.
    """
    if params["weight"] != 1:
        raise ValueError("Audit requires frozen full anchoring")
    model = ArrayPredictor(np.full(len(evaluation), 0.5))
    adapter = PollAnchoredRegressor(model, **params).fit(train)
    details = adapter.predict_components(evaluation.drop(columns=["yes_share"]))
    weights = adapter._weights(evaluation.reset_index(drop=True)).fillna(0).to_numpy(float)
    groups = []
    for positions in evaluation.reset_index(drop=True).groupby("vote_key", sort=False).indices.values():
        pos = np.asarray(positions, dtype=int)
        if bool(details.poll_applied.iloc[pos[0]]):
            w = weights[pos]
            groups.append((pos, w / w.sum(), float(details.national_target_mean.iloc[pos[0]])))
    return adapter, groups


def anchor_fast(pred, groups):
    output = pred.copy()
    for pos, weights, target in groups:
        p = pred[pos]
        lo, hi = -float(p.max()), 1 - float(p.min())
        # 48 iterations already exceed the required tolerance.
        for _ in range(48):
            mid = (lo + hi) / 2
            if weights @ np.clip(p + mid, 0, 1) < target:
                lo = mid
            else:
                hi = mid
        output[pos] = np.clip(p + (lo + hi) / 2, 0, 1)
    return output


def prepare_fold(a, b, numeric, categorical, params):
    """Mirror the exact original ObjectProfileRegressor.fit data path."""
    profile = ObjectProfileRegressor(numeric, categorical, **params)
    profile._validate_feature_lists()
    objects, row_votes, row_communes = profile._object_table(a)
    target = a.yes_share.to_numpy(float)
    outcomes = pd.DataFrame({"vote_id": row_votes, "municipality_id": row_communes, "value": target})
    matrix = outcomes.pivot(index="vote_id", columns="municipality_id", values="value").reindex(objects.index)
    mu = matrix.mean(axis=1).to_numpy(float)
    values = matrix.to_numpy(float)
    residuals = np.where(np.isnan(values), mu[:, None], values) - mu[:, None]
    pca = PCA(n_components=params["dimensions"], svd_solver="randomized",
              random_state=params["random_state"])
    with threadpool_limits(limits=2):
        coefficients = pca.fit_transform(residuals)
    preprocessor = profile._make_preprocessor()
    train_x = preprocessor.fit_transform(objects)
    validation_objects, val_votes, val_communes = profile._object_table(b)
    val_x = preprocessor.transform(validation_objects)
    train_index = objects.index.get_indexer(row_votes)
    train_communes = matrix.columns.get_indexer(row_communes)
    val_index = validation_objects.index.get_indexer(val_votes)
    val_muni = matrix.columns.get_indexer(val_communes)
    return {
        "train_x": train_x, "val_x": val_x,
        "heads": np.column_stack([mu, coefficients]),
        "pca": pca, "train_idx": train_index, "train_muni": train_communes,
        "val_idx": val_index, "val_muni": val_muni,
        "train_y": target, "val_y": b.yes_share.to_numpy(float),
        "train_ids": objects.index.astype(str).tolist(),
        "val_ids": validation_objects.index.astype(str).tolist(),
    }


def reconstruct(heads, pca, object_idx, municipality_idx):
    profiles = pca.mean_[None, :] + heads[:, 1:] @ pca.components_
    prediction = heads[object_idx, 0].astype(float).copy()
    known = municipality_idx >= 0
    prediction[known] += profiles[object_idx[known], municipality_idx[known]]
    return np.clip(prediction, 0, 1)


def diagnostics(y, prediction, idx, n):
    """Macro object MAE plus decomposition of level vs centered local errors."""
    error = (prediction - y) * 100
    sizes = np.bincount(idx, minlength=n)
    if np.any(sizes == 0):
        raise ValueError("Missing object in scoring table")
    means = np.bincount(idx, weights=error, minlength=n) / sizes
    mae = np.bincount(idx, weights=np.abs(error), minlength=n) / sizes
    local = np.bincount(idx, weights=np.abs(error - means[idx]), minlength=n) / sizes
    mse = np.bincount(idx, weights=error ** 2, minlength=n) / sizes
    centered_mse = np.bincount(idx, weights=(error - means[idx]) ** 2, minlength=n) / sizes
    return {
        "mae": float(mae.mean()),
        "mean_abs_bias": float(np.abs(means).mean()),
        "centered_mae": float(local.mean()),
        "mse": float(mse.mean()),
        "centered_mse": float(centered_mse.mean()),
    }, mae


def run(base, output, feature_set):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve previous experiments")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    check_plan(plan, json.loads(V3_PLAN.read_text(encoding="utf-8")))
    data, extras, numeric, categorical, _ = prepare_data(
        base, EXTRAS, HISTORICAL, V4, CURRENT_POLLS, HISTORICAL_POLLS, plan
    )
    output.mkdir(parents=True, exist_ok=True)
    rows, object_rows = [], []
    for window in plan["validation_windows"]:
        train = data[data.vote_date.lt(window["start"])]
        evaluation = data[data.vote_date.between(window["start"], window["end"])]
        if train.empty or evaluation.empty or train.vote_date.max() >= evaluation.vote_date.min():
            raise ValueError("Chronological boundary failed")
        a, b, use_n, use_c, _, coverage = fold_features(
            train, evaluation, extras, numeric, categorical, FEATURE_SETS[feature_set],
            plan["mechanism_min_support_in_training_objects"],
        )
        params = dict(plan["regressor_parameters"])
        fold = prepare_fold(a, b, use_n, use_c, params)
        anchor, groups = poll_context(a, b, plan["frozen_poll_parameters"])
        nt, nv = len(fold["train_ids"]), len(fold["val_ids"])
        for name, overrides in GRID.items():
            estimator_params = {**params, **overrides, "n_estimators": max(STEPS)}
            prototype = ObjectProfileRegressor(use_n, use_c, **estimator_params)
            models = []
            with threadpool_limits(limits=2):
                for values in fold["heads"].T:
                    model = prototype._make_regressor()
                    model.fit(fold["train_x"], values)
                    models.append(model)
            for step in STEPS:
                with threadpool_limits(limits=2):
                    tr_heads = np.column_stack([
                        m.predict(fold["train_x"], iteration_range=(0, step)) for m in models
                    ])
                    va_heads = np.column_stack([
                        m.predict(fold["val_x"], iteration_range=(0, step)) for m in models
                    ])
                    tr = reconstruct(tr_heads, fold["pca"], fold["train_idx"], fold["train_muni"])
                    va = reconstruct(va_heads, fold["pca"], fold["val_idx"], fold["val_muni"])
                adjusted = anchor_fast(va, groups)
                if name == "depth_6" and step == 300:
                    # Check both the reconstructed baseline and fast anchor
                    # against the public, unchanged production implementation.
                    original = ObjectProfileRegressor(use_n, use_c, **params)
                    with threadpool_limits(limits=2):
                        original.fit(a)
                        expected = original.predict(b.drop(columns=["yes_share"]))
                    np.testing.assert_allclose(va, expected, atol=1e-7, rtol=1e-6)
                    anchor.base_model = ArrayPredictor(expected)
                    expected_adjusted = anchor.predict(b.drop(columns=["yes_share"]))
                    np.testing.assert_allclose(adjusted, expected_adjusted, atol=1e-7, rtol=1e-6)
                tr_metrics, _ = diagnostics(fold["train_y"], tr, fold["train_idx"], nt)
                va_metrics, _ = diagnostics(fold["val_y"], va, fold["val_idx"], nv)
                poll_metrics, per_object = diagnostics(
                    fold["val_y"], adjusted, fold["val_idx"], nv
                )
                row = {
                    "feature_set": feature_set, "window": window["name"],
                    "configuration": name, "trees": step,
                    "train_objects": nt, "validation_objects": nv,
                    "encoded_features": int(fold["train_x"].shape[1]),
                    "annotated_train": coverage["train_annotated"],
                    "depth": estimator_params["max_depth"],
                    "l2": estimator_params["reg_lambda"],
                    "min_child_weight": estimator_params.get("model_params", {}).get("min_child_weight", 1),
                    "learning_rate": estimator_params.get("learning_rate", 0.03),
                }
                for prefix, result in [("train", tr_metrics), ("validation", va_metrics), ("polled", poll_metrics)]:
                    row.update({prefix + "_" + k: v for k, v in result.items()})
                rows.append(row)
                for vote_id, mae in zip(fold["val_ids"], per_object, strict=True):
                    object_rows.append({
                        "feature_set": feature_set, "window": window["name"],
                        "configuration": name, "trees": step, "vote_id": vote_id,
                        "mae_pp": float(mae),
                    })
            print("COMPLETED", feature_set, window["name"], name, flush=True)
        pd.DataFrame(rows).to_csv(output / "fold_metrics.csv", index=False)
    detail = pd.DataFrame(rows)
    grouped = []
    for (config, step), group in detail.groupby(["configuration", "trees"], sort=False):
        row = {"feature_set": feature_set, "configuration": config, "trees": int(step)}
        for col in detail.columns:
            if col.startswith(("train_", "validation_", "polled_")) and col not in ("train_objects", "validation_objects"):
                weight = "train_objects" if col.startswith("train_") else "validation_objects"
                row[col] = float(np.average(group[col], weights=group[weight]))
        grouped.append(row)
    table = pd.DataFrame(grouped)
    reference = table[(table.configuration == "depth_6") & (table.trees == 300)].iloc[0]
    expected_score = {"v3": 7.618292700184025, "v5": 7.626471087954747}[feature_set]
    if not np.isclose(reference.polled_mae, expected_score, atol=0.0002, rtol=0):
        raise ValueError(f"Frozen baseline mismatch {reference.polled_mae}")
    table.to_csv(output / "curves.csv", index=False)
    pd.DataFrame(object_rows).to_csv(output / "object_metrics.csv", index=False)
    manifest = {
        "status": "complete", "feature_set": feature_set,
        "grid": GRID, "tree_checkpoints": list(STEPS),
        "protocol": plan, "source_sha256": sha(Path(__file__)),
        "prepared_data_sha256": sha(base / "dataset.parquet"),
        "baseline_reproduced": True,
        "comparison_targets_loaded": False,
        "strict_forecast_ready": False,
        "metrics": grouped,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("CURVES", json.dumps(grouped), flush=True)
    print("BEST DEVELOPMENT", table.sort_values("polled_mae").head(8).to_string(index=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--feature-set", choices=FEATURE_SETS, required=True)
    args = parser.parse_args()
    run(args.base, args.output, args.feature_set)


if __name__ == "__main__":
    main()

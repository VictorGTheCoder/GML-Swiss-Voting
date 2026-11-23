"""Chronological recency weighting and lagged trend ablations for the V3 profile.

Experimental only: identical 66 validation objects, PCA5, XGBoost parameters
and poll anchor. Train heads get one weight per object, not per commune.
Every history feature uses strictly earlier objects from the current train.
Validation outcomes are never supplied to the history feature builder.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from sklearn.utils.extmath import randomized_svd
from threadpoolctl import threadpool_limits

from scripts.common.config import ROOT
from scripts.modeling.audit_xgboost_capacity import (
    anchor_fast,
    diagnostics,
    poll_context,
    prepare_fold,
    reconstruct,
)
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

# Fixed before scores. Changing the basis is isolated from weighting the heads.
SUITES = {
    "weights": {
        "reference": ("none", None, False),
        "weight20": ("none", 20, False),
        "weight10": ("none", 10, False),
        "weight5": ("none", 5, False),
        "weight2": ("none", 2, False),
    },
    "trends": {
        "calendar": ("calendar", None, False),
        "history": ("history", None, False),
        "history_weight20": ("history", 20, False),
        "history_weight10": ("history", 10, False),
        "history_weight5": ("history", 5, False),
    },
    "basis": {
        "basis_weight10": ("none", 10, True),
        "basis_weight5": ("none", 5, True),
        "history_basis_weight10": ("history", 10, True),
    },
}
DOMAIN = ["object_domain_1", "object_domain_2", "object_domain_3"]
LABEL_COLUMNS = ["mean_yes", "fr_de"]
CALENDAR_COLUMNS = ["time_year"]
HISTORY_COLUMNS = CALENDAR_COLUMNS + [
    "time_recent_mean_yes", "time_delta_mean_yes",
    "time_similar_recent_mean_yes", "time_similar_delta_mean_yes",
    "time_recent_fr_de", "time_delta_fr_de",
    "time_similar_recent_fr_de", "time_similar_delta_fr_de",
    "time_similar_recent_support", "time_similar_older_support",
]


def recency_weights(dates, cutoff, half_life):
    days = (pd.Timestamp(cutoff) - pd.DatetimeIndex(dates)).days.to_numpy(float)
    if len(days) == 0 or not np.isfinite(days).all() or (days <= 0).any():
        raise ValueError("Training objects must strictly precede the fold cutoff")
    if half_life is None:
        return np.ones(len(days))
    if not np.isfinite(half_life) or half_life <= 0:
        raise ValueError("Half-life must be positive")
    # Normalizing makes total weight equal to the number of objects, preserving
    # the scale of the existing regularization more closely.
    w = np.exp2(-days / (365.2425 * half_life))
    return w / w.mean()


def effective_n(w):
    return float(w.sum() ** 2 / np.square(w).sum())


def object_descriptors(frame):
    """Allowlisted object identity and metadata only, no target."""
    directions = sorted(c for c in frame if c.startswith("political_direction_"))
    fields = ["vote_id", "vote_date", *DOMAIN, *directions]
    meta = frame[fields].drop_duplicates().copy()
    if meta.vote_id.duplicated().any():
        raise ValueError("Object descriptors vary within vote")
    meta["vote_id"] = meta.vote_id.astype(str)
    return meta.set_index("vote_id"), directions


def history_labels(train, language):
    """Aggregate historical communal outcomes into object-level level and shape."""
    rows = train[["vote_id", "municipality_id", "yes_share"]].copy()
    rows["language"] = rows.municipality_id.astype(str).map(language)
    means = rows.groupby("vote_id").yes_share.mean()
    regions = rows.groupby(["vote_id", "language"]).yes_share.mean().unstack()
    if not {"1", "2"}.issubset(regions.columns):
        raise ValueError("Expected OFS German/French language-region codes")
    return pd.DataFrame({
        "mean_yes": means, "fr_de": regions["2"] - regions["1"],
    })


def domains(row):
    values = {str(row[c]).strip() for c in DOMAIN if pd.notna(row[c])}
    return values - {"", ".", "nan", "<NA>"}


def matching_weights(history, query, directions, *, cached=None):
    """Similarity fixed in advance: shared major theme AND endorsement agreement.

    Exact outcome values never influence the selection of similar old objects.
    Unknown parties are not treated as negative recommendations.
    """
    if cached is None:
        cached = (
            [domains(row) for _, row in history.iterrows()],
            history[directions].to_numpy(dtype=float, na_value=np.nan),
        )
    prior_domains, p = cached
    query_domains = domains(query)
    theme = np.array([
        len(query_domains & other) / len(query_domains | other)
        if query_domains | other else 0.0
        for other in prior_domains
    ])
    q = query[directions].to_numpy(dtype=float, na_value=np.nan)
    valid = np.isin(q, [-1, 1])[None, :] & np.isin(p, [-1, 1])
    count = valid.sum(axis=1)
    agreement = np.divide(
        ((q[None, :] == p) & valid).sum(axis=1), count,
        out=np.zeros(len(p)), where=count > 0,
    )
    return theme * (0.25 + 0.75 * agreement)


def weighted_mean(values, w):
    values = np.asarray(values, dtype=float)
    valid = np.isfinite(values) & (w > 0)
    if not valid.any():
        return float("nan")
    return float(np.average(values[valid], weights=w[valid]))


def trend_features(query_meta, history_meta, labels, directions, block):
    """Only past TRAIN outcomes are admissible, even for later validation dates."""
    if block not in {"calendar", "history"}:
        raise ValueError("Unknown time feature block")
    if not history_meta.index.is_unique or not labels.index.is_unique:
        raise ValueError("Duplicate historical vote")
    # Do not accept any evaluation result column via query metadata.
    allowed = {"vote_date", *DOMAIN, *directions}
    if set(query_meta.columns) != allowed or set(history_meta.columns) != allowed:
        raise ValueError("Unexpected descriptor fields")
    if set(labels.columns) != set(LABEL_COLUMNS):
        raise ValueError("Unexpected history labels")
    history = history_meta.join(labels, how="left", validate="one_to_one")
    if history.mean_yes.isna().any():
        raise ValueError("Missing past vote outcomes")
    dates = pd.DatetimeIndex(history.vote_date)
    cached = (
        [domains(row) for _, row in history.iterrows()],
        history[directions].to_numpy(dtype=float, na_value=np.nan),
    )
    result = []
    for vote_id, query in query_meta.iterrows():
        stamp = pd.Timestamp(query.vote_date)
        row = {"vote_id": str(vote_id),
               "time_year": (stamp - pd.Timestamp("1990-01-01")).days / 365.2425}
        if block == "history":
            ages = (stamp - dates).days.to_numpy(float) / 365.2425
            # Strict positive age removes the query itself and every same-day object.
            recent = (ages > 0) & (ages <= 5)
            older = (ages > 5) & (ages <= 15)
            similarity = matching_weights(history, query, directions, cached=cached)
            for label in LABEL_COLUMNS:
                values = history[label].to_numpy(float)
                m1, m2 = weighted_mean(values, recent.astype(float)), weighted_mean(values, older.astype(float))
                s1, s2 = weighted_mean(values, similarity * recent), weighted_mean(values, similarity * older)
                row["time_recent_" + label] = m1
                row["time_delta_" + label] = m1 - m2
                row["time_similar_recent_" + label] = s1
                row["time_similar_delta_" + label] = s1 - s2
            row["time_similar_recent_support"] = float(np.sum((similarity > 0) & recent))
            row["time_similar_older_support"] = float(np.sum((similarity > 0) & older))
        result.append(row)
    columns = CALENDAR_COLUMNS if block == "calendar" else HISTORY_COLUMNS
    return pd.DataFrame(result, columns=["vote_id", *columns])


def add_time_block(train, evaluation, numeric, block, language):
    if block == "none":
        return train, evaluation, list(numeric)
    train_meta, directions = object_descriptors(train)
    eval_meta, eval_directions = object_descriptors(evaluation.drop(columns=["yes_share"]))
    if directions != eval_directions:
        raise ValueError("Inconsistent directional features")
    labels = history_labels(train, language)
    t = trend_features(train_meta, train_meta, labels, directions, block)
    v = trend_features(eval_meta, train_meta, labels, directions, block)
    a = train.merge(t, on="vote_id", how="left", validate="many_to_one", sort=False)
    b = evaluation.merge(v, on="vote_id", how="left", validate="many_to_one", sort=False)
    for original, merged in [(train, a), (evaluation, b)]:
        pd.testing.assert_frame_equal(
            original[["vote_id", "municipality_id"]].reset_index(drop=True),
            merged[["vote_id", "municipality_id"]].reset_index(drop=True),
        )
    return a, b, list(numeric) + [c for c in t if c != "vote_id"]


def weighted_profile(fold, train, w, params):
    """Fit a recency-weighted PCA of past, centered municipal residuals only."""
    matrix = train.pivot(index="vote_id", columns="municipality_id", values="yes_share")
    matrix = matrix.reindex(fold["train_ids"])
    y = matrix.to_numpy(float)
    mu = np.nanmean(y, axis=1)
    r = np.where(np.isnan(y), mu[:, None], y) - mu[:, None]
    if not np.allclose(mu, fold["heads"][:, 0]):
        raise ValueError("Object order mismatch")
    if not np.array_equal(matrix.columns.astype(str).to_numpy(),
                          np.array(sorted(train.municipality_id.astype(str).unique()))):
        raise ValueError("Unexpected municipal order")
    center = np.average(r, axis=0, weights=w)
    centered = r - center
    # Weighted least-squares PCA: scale rows by sqrt(weight) before SVD;
    # the head regression targets themselves remain on their original scale.
    _, _, components = randomized_svd(
        centered * np.sqrt(w[:, None]), n_components=params["dimensions"],
        random_state=params["random_state"], n_iter=7,
    )
    heads = np.column_stack([mu, centered @ components.T])
    return SimpleNamespace(mean_=center, components_=components), heads


def run(base, output, suite):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Do not overwrite an experiment")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    check_plan(plan, json.loads(V3_PLAN.read_text(encoding="utf-8")))
    data, _, numeric, categorical, _ = prepare_data(
        base, EXTRAS, HISTORICAL, V4, CURRENT_POLLS, HISTORICAL_POLLS, plan
    )
    typologies = pd.read_parquet(
        ROOT / "data/processed/typologies/commune_typologies.parquet",
        columns=["municipality_id", "language_region"],
    )
    language = typologies.assign(municipality_id=typologies.municipality_id.astype(str)).set_index(
        "municipality_id", verify_integrity=True
    ).language_region.astype(str)
    output.mkdir(parents=True, exist_ok=True)
    rows, per_object = [], []
    params = dict(plan["regressor_parameters"])
    for window in plan["validation_windows"]:
        train = data[data.vote_date.lt(window["start"])]
        evaluation = data[data.vote_date.between(window["start"], window["end"])]
        if train.empty or evaluation.empty or train.vote_date.max() >= evaluation.vote_date.min():
            raise ValueError("Invalid chronology")
        _, groups = poll_context(train, evaluation, plan["frozen_poll_parameters"])
        date_lookup = train[["vote_id", "vote_date"]].drop_duplicates().set_index("vote_id").vote_date
        val_lookup = evaluation[["vote_id", "vote_date", "poll_available"]].drop_duplicates().set_index("vote_id")
        cached = {}
        for name, (block, half_life, basis) in SUITES[suite].items():
            if block not in cached:
                a, b, use_n = add_time_block(train, evaluation, numeric, block, language)
                cached[block] = (prepare_fold(a, b, use_n, categorical, params), use_n)
            fold, use_n = cached[block]
            weights = recency_weights(date_lookup.loc[fold["train_ids"]], window["start"], half_life)
            pca, targets = fold["pca"], fold["heads"]
            if basis:
                with threadpool_limits(limits=2):
                    pca, targets = weighted_profile(fold, train, weights, params)
            prototype = ObjectProfileRegressor(use_n, categorical, **params)
            with threadpool_limits(limits=2):
                fitted = []
                for y in targets.T:
                    model = prototype._make_regressor()
                    if half_life is None:
                        model.fit(fold["train_x"], y)
                    else:
                        model.fit(fold["train_x"], y, sample_weight=weights)
                    fitted.append(model)
                train_heads = np.column_stack([m.predict(fold["train_x"]) for m in fitted])
                val_heads = np.column_stack([m.predict(fold["val_x"]) for m in fitted])
                tr = reconstruct(train_heads, pca, fold["train_idx"], fold["train_muni"])
                va = reconstruct(val_heads, pca, fold["val_idx"], fold["val_muni"])
            anchored = anchor_fast(va, groups)
            nt, nv = len(fold["train_ids"]), len(fold["val_ids"])
            tr_metric, _ = diagnostics(fold["train_y"], tr, fold["train_idx"], nt)
            st_metric, _ = diagnostics(fold["val_y"], va, fold["val_idx"], nv)
            poll_metric, per = diagnostics(fold["val_y"], anchored, fold["val_idx"], nv)
            row = {
                "configuration": name, "window": window["name"], "half_life": half_life,
                "trend_block": block, "weighted_pca": basis, "train_objects": nt,
                "effective_train_objects": effective_n(weights), "validation_objects": nv,
                "encoded_features": int(fold["train_x"].shape[1]),
            }
            for prefix, metrics in [("train", tr_metric), ("validation", st_metric), ("polled", poll_metric)]:
                row.update({prefix + "_" + k: v for k, v in metrics.items()})
            rows.append(row)
            for vote, mae in zip(fold["val_ids"], per, strict=True):
                per_object.append({
                    "variant": name, "vote_id": vote,
                    "vote_date": str(val_lookup.loc[vote, "vote_date"].date()),
                    "poll_available": int(val_lookup.loc[vote, "poll_available"]),
                    "mae_pp": float(mae),
                })
            print("FOLD", json.dumps(row, allow_nan=False), flush=True)
    detail = pd.DataFrame(rows)
    objects = pd.DataFrame(per_object)
    summary = []
    for name, g in detail.groupby("configuration", sort=False):
        row = {"configuration": name}
        for c in detail:
            if c.startswith(("train_", "validation_", "polled_")) and c not in ("train_objects", "validation_objects"):
                wcol = "train_objects" if c.startswith("train_") else "validation_objects"
                row[c] = float(np.average(g[c], weights=g[wcol]))
        row["effective_train_objects"] = float(g.effective_train_objects.mean())
        sub = objects[objects.variant.eq(name)]
        if len(sub) != 66 or sub.vote_id.nunique() != 66 or sub.vote_date.nunique() != 23:
            raise ValueError("Wrong evaluation population")
        row["with_poll_mae"] = float(sub[sub.poll_available.eq(1)].mae_pp.mean())
        row["without_poll_mae"] = float(sub[sub.poll_available.eq(0)].mae_pp.mean())
        summary.append(row)
    result = pd.DataFrame(summary)
    if suite == "weights":
        baseline = result[result.configuration.eq("reference")].iloc[0]
        if not np.isclose(baseline.polled_mae, 7.618292700184025, atol=0.0002, rtol=0):
            raise ValueError("Original V3 reference did not reproduce")
        for name in SUITES[suite]:
            if name != "reference":
                print("GAIN", name, paired_date_bootstrap(objects, "reference", name), flush=True)
    detail.to_csv(output / "fold_metrics.csv", index=False)
    objects.to_csv(output / "object_metrics.csv", index=False)
    result.to_csv(output / "summary.csv", index=False)
    manifest = {
        "suite": suite, "status": "complete", "strict_forecast_ready": False,
        "comparison_targets_loaded": False, "plan": plan, "configurations": SUITES[suite],
        "prepared_data_sha256": sha(base / "dataset.parquet"), "code_sha256": sha(Path(__file__)),
        "history_rule": "prior train dates only; never previous evaluation outcomes",
        "summary": summary,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    print("SUMMARY", json.dumps(summary, allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--suite", choices=SUITES, required=True)
    args = parser.parse_args()
    run(args.base, args.output, args.suite)


if __name__ == "__main__":
    main()

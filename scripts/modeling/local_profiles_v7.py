"""Train-only local recency/similarity weighting and representative communes.

Keep the V3 national-level head fitted on all prior objects uniformly.
Municipal representativeness is learned from prior aggregate voting results,
with leave-one-municipality-out reference shares. No concurrent vote result
is used to predict any municipality, and validation is never reweighted.
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
from scripts.modeling.audit_xgboost_capacity import anchor_fast, diagnostics, poll_context, prepare_fold, reconstruct
from scripts.modeling.diagnose_v5_errors import load_outcomes
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
from scripts.modeling.temporal_drift_v6 import (
    domains,
    effective_n,
    matching_weights,
    object_descriptors,
    recency_weights,
)

# All variants fixed before any new scores.
SUITES = {
    "local": (
        "reference", "local_weight20", "local_weight10", "local_weight5",
        "local_pca10", "local_pca5", "local_pca_only10", "local_pca_only5",
    ),
    "similarity": (
        "reference", "similarity_xgb", "similarity_xgb_recent10",
        "analog_blend25", "local_drift25",
    ),
    "representative": (
        "reference", "national_basis", "cantonal_basis", "combined_basis",
        "national_panel_head",
    ),
}
REP_MIN_COVERAGE = 0.8
REP_MIN_OBJECTS = 30
PANEL_SIZES = (1, 5, 20)


def historical_matrix(train, ids):
    m = train.pivot(index="vote_id", columns="municipality_id", values="yes_share").reindex(ids)
    y = m.to_numpy(float)
    mu = np.nanmean(y, axis=1)
    if not np.isfinite(mu).all():
        raise ValueError("Missing object in historical matrix")
    r = y - mu[:, None]
    return m.columns.astype(str).to_numpy(), mu, r


def metric_basis(r, mu, row_weights, col_weights, dimensions, seed):
    """Weighted low-rank approximation, then invert municipal column scaling.

    row_weights changes historical importance; col_weights changes the geometry
    of PCA, not the final scoring metric. Missing historical cells use zero
    residual, the same policy as the original profile.
    """
    if (row_weights <= 0).any() or (col_weights <= 0).any():
        raise ValueError("Weights must be strictly positive")
    complete = np.nan_to_num(r, nan=0.0)
    center = np.average(complete, axis=0, weights=row_weights)
    centered = complete - center
    sqrt_c = np.sqrt(col_weights)
    scaled = centered * sqrt_c[None, :]
    _, _, v = randomized_svd(
        scaled * np.sqrt(row_weights[:, None]), n_components=dimensions,
        random_state=seed, n_iter=7,
    )
    # Coordinates are fitted in weighted municipal space, then recovered on
    # the original percentage scale. No municipality is dropped.
    heads = np.column_stack([mu, scaled @ v.T])
    return SimpleNamespace(mean_=center, components_=v / sqrt_c[None, :]), heads


def representative_errors(rows, level):
    """Historical municipal vs *rest of area* yes shares, ballot-weighted."""
    if level not in ("national", "canton"):
        raise ValueError("Unknown geographic level")
    cols = ["vote_id", "municipality_id", "canton", "votes_yes", "votes_no"]
    a = rows[cols].copy()
    if a.duplicated(["vote_id", "municipality_id"]).any():
        raise ValueError("Duplicate municipal vote")
    a["ballots"] = a.votes_yes + a.votes_no
    if (a.ballots <= 0).any():
        raise ValueError("Invalid historical ballots")
    keys = ["vote_id"] if level == "national" else ["vote_id", "canton"]
    group = a.groupby(keys, dropna=False)
    denom = group.ballots.transform("sum") - a.ballots
    other_yes = group.votes_yes.transform("sum") - a.votes_yes
    a["rest_share"] = other_yes / denom.where(denom > 0)
    a["error"] = a.votes_yes / a.ballots - a.rest_share
    return a


def representative_rank(train, level):
    a = representative_errors(train, level)
    a["abs_error"] = a.error.abs()
    rank = a.groupby(["municipality_id", "canton"], as_index=False).agg(
        n=("error", "count"), mae=("abs_error", "mean"),
        bias=("error", "mean"), ballots=("ballots", "median"),
    )
    if rank.municipality_id.duplicated().any():
        raise ValueError("Municipality changes canton in fixed geography")
    if level == "national":
        rank["possible"] = train.vote_id.nunique()
    else:
        rank["possible"] = rank.canton.map(train.groupby("canton").vote_id.nunique())
    rank["coverage"] = rank.n / rank.possible
    rank["eligible"] = (
        rank.n.ge(REP_MIN_OBJECTS) & rank.coverage.ge(REP_MIN_COVERAGE)
        & rank.mae.notna()
    )
    rank["weight"] = 1.0
    eligible = rank[rank.eligible]
    groups = [(None, eligible)] if level == "national" else list(eligible.groupby("canton"))
    for _, g in groups:
        if len(g) < 3:
            continue
        # Bounded weights, one common scale within each geographic group.
        # Low MAE receives high weight; rank is less sensitive to outliers.
        quality = 1 - (g.mae.rank(method="average") - 1) / (len(g) - 1)
        w = 0.5 + 1.5 * quality
        rank.loc[g.index, "weight"] = w / w.mean()
    return rank


def panel_eval(rank, evaluation, level, rng):
    """Diagnostic using *observed* held-out panel results, NOT prediction.

    Panels/ranks and random alternatives are chosen solely from the train.
    Held-out panel mean is compared to the vote-weighted aggregate of all
    remaining communes, excluding the panel itself. Report matched random
    panel expectations and coverage. Single-commune canton is undefined.
    """
    key = "national" if level == "national" else "canton"
    all_eval = evaluation.assign(
        ballots=evaluation.votes_yes + evaluation.votes_no,
        share=evaluation.votes_yes / (evaluation.votes_yes + evaluation.votes_no),
    )
    eligible = rank[rank.eligible].copy()
    groups = [("CH", eligible)] if level == "national" else list(eligible.groupby("canton"))
    records = []
    for region, g in groups:
        g = g.sort_values(["mae", "municipality_id"])
        if len(g) < 2:
            continue
        sub = all_eval if level == "national" else all_eval[all_eval.canton.eq(region)]
        ids = g.municipality_id.astype(str).tolist()
        for k in PANEL_SIZES if level == "national" else (1, 3):
            if k >= len(ids):
                continue
            panel = ids[:k]
            selection = np.vstack([
                np.arange(k),
                *[rng.choice(len(ids), size=k, replace=False) for _ in range(50)],
            ])
            for vote, vote_rows in sub.groupby("vote_id"):
                lookup = vote_rows.set_index("municipality_id").reindex(ids)
                total_yes = float(vote_rows.votes_yes.sum())
                total_ballots = float(vote_rows.ballots.sum())
                shares = lookup.share.to_numpy(float)[selection]
                ballots = lookup.ballots.to_numpy(float)[selection]
                yes = lookup.votes_yes.to_numpy(float)[selection]
                remainder = total_ballots - ballots.sum(axis=1)
                valid = np.isfinite(shares).all(axis=1) & (remainder > 0)
                rest = np.divide(total_yes - yes.sum(axis=1), remainder,
                                 out=np.full(len(selection), np.nan), where=valid)
                errors = np.abs(shares.mean(axis=1) - rest) * 100
                actual = errors[0]
                finite = errors[1:][np.isfinite(errors[1:])]
                if np.isfinite(actual) and len(finite):
                    records.append({
                        "level": key, "area": str(region), "k": k, "vote_id": str(vote),
                        "panel_error_pp": float(actual), "random_error_pp": float(finite.mean()),
                        "panel_ids": "|".join(panel), "random_panels_valid": len(finite),
                    })
    return records


def similarity_matrix(train_meta, query_meta, directions):
    cached = (
        [domains(row) for _, row in train_meta.iterrows()],
        train_meta[directions].to_numpy(dtype=float, na_value=np.nan),
    )
    return np.stack([
        matching_weights(train_meta, query, directions, cached=cached)
        for _, query in query_meta.iterrows()
    ])


def similarity_sample_weights(sim, recent=None):
    """Keep every object, boost matching topics and compatible party positions."""
    if (sim < 0).any() or (sim > 1 + 1e-8).any():
        raise ValueError("Invalid similarity")
    w = 0.25 + 0.75 * sim
    if recent is not None:
        w *= recent
    return w / w.mean()


def fit_heads(proto, x, targets, vx, weights=None, *, global_only=False):
    results = []
    for y in (targets[:, :1] if global_only else targets).T:
        model = proto._make_regressor()
        if weights is None:
            model.fit(x, y)
        else:
            model.fit(x, y, sample_weight=weights)
        results.append(model.predict(vx))
    return np.column_stack(results)


def local_drift(r, dates, query_dates):
    """Past-only municipality-specific change in historical centered outcomes."""
    results = []
    for date in query_dates:
        ages = (pd.Timestamp(date) - pd.DatetimeIndex(dates)).days.to_numpy(float) / 365.2425
        recent, older = (ages > 0) & (ages <= 5), (ages > 5) & (ages <= 15)
        means = []
        for mask in (recent, older):
            selected = r[mask]
            counts = np.isfinite(selected).sum(axis=0)
            means.append(np.divide(np.nansum(selected, axis=0), counts,
                                   out=np.full(r.shape[1], np.nan), where=counts >= 5))
        delta = np.nan_to_num(means[0] - means[1], nan=0.0)
        results.append(delta - delta.mean())
    return np.stack(results)


def add_local_adjustment(pred, fold, adjustment):
    result = pred.copy()
    known = fold["val_muni"] >= 0
    offset = np.zeros(len(result))
    offset[known] = adjustment[fold["val_idx"][known], fold["val_muni"][known]]
    # Keep the equal-municipality level unchanged before clipping.
    counts = np.bincount(fold["val_idx"], minlength=len(fold["val_ids"]))
    means = np.bincount(fold["val_idx"], weights=offset, minlength=len(counts)) / counts
    return np.clip(result + offset - means[fold["val_idx"]], 0, 1)


def run(base, output, suite):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve previous experiments")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    check_plan(plan, json.loads(V3_PLAN.read_text(encoding="utf-8")))
    data, _, numeric, categorical, _ = prepare_data(
        base, EXTRAS, HISTORICAL, V4, CURRENT_POLLS, HISTORICAL_POLLS, plan
    )
    # Real ballot counts are only necessary for the representation experiment.
    if suite == "representative":
        counts = load_outcomes()
        keys = ["municipality_id", "vote_id"]
        counts = data[keys + ["vote_date", "yes_share"]].merge(
            counts[keys + ["canton", "votes_yes", "votes_no", "yes_share"]],
            on=keys, validate="one_to_one", how="left", suffixes=("", "_ofs"),
        )
        if counts.votes_yes.isna().any() or not np.allclose(counts.yes_share, counts.yes_share_ofs):
            raise ValueError("OFS counts do not match the modeling population")
        names = pd.read_parquet(ROOT / "data/processed/typologies/commune_typologies.parquet",
                                columns=["municipality_id", "commune_name"])
        names = names.assign(municipality_id=names.municipality_id.astype(str)).set_index(
            "municipality_id", verify_integrity=True
        ).commune_name
    output.mkdir(parents=True, exist_ok=True)
    records, object_rows, rankings, panels = [], [], [], []
    params = dict(plan["regressor_parameters"])
    for window in plan["validation_windows"]:
        train = data[data.vote_date.lt(window["start"])]
        evaluation = data[data.vote_date.between(window["start"], window["end"])]
        if train.empty or evaluation.empty or train.vote_date.max() >= evaluation.vote_date.min():
            raise ValueError("Invalid chronology")
        fold = prepare_fold(train, evaluation, numeric, categorical, params)
        _, groups = poll_context(train, evaluation, plan["frozen_poll_parameters"])
        date_lookup = train[["vote_id", "vote_date"]].drop_duplicates().set_index("vote_id").vote_date
        val_lookup = evaluation[["vote_id", "vote_date", "poll_available"]].drop_duplicates().set_index("vote_id")
        train_dates = date_lookup.loc[fold["train_ids"]]
        val_dates = val_lookup.loc[fold["val_ids"], "vote_date"]
        nt, nv = len(fold["train_ids"]), len(fold["val_ids"])
        munis, mu, residuals = historical_matrix(train, fold["train_ids"])
        np.testing.assert_allclose(mu, fold["heads"][:, 0], atol=1e-10)
        uniform, municipal_uniform = np.ones(nt), np.ones(len(munis))
        proto = ObjectProfileRegressor(numeric, categorical, **params)
        with threadpool_limits(limits=2):
            original = fit_heads(proto, fold["train_x"], fold["heads"], fold["val_x"])
        base_prediction = reconstruct(original, fold["pca"], fold["val_idx"], fold["val_muni"])
        if suite == "similarity":
            tm, directions = object_descriptors(train)
            qm, d2 = object_descriptors(evaluation.drop(columns=["yes_share"]))
            if directions != d2:
                raise ValueError("Feature mismatch")
            sim = similarity_matrix(tm.loc[fold["train_ids"]], qm.loc[fold["val_ids"]], directions)
        if suite == "representative":
            past_counts = counts[counts.vote_date.lt(window["start"])]
            test_counts = counts[counts.vote_date.between(window["start"], window["end"])]
            ranks = {level: representative_rank(past_counts, level) for level in ("national", "canton")}
            for level, ranking in ranks.items():
                ranking["window"] = window["name"]
                ranking["level"] = level
                ranking["commune_name"] = ranking.municipality_id.map(names)
                # Evaluate only after the training-only rank is frozen.
                heldout = representative_errors(test_counts, level)
                heldout["abs_error"] = heldout.error.abs()
                quality = heldout.groupby("municipality_id").agg(
                    heldout_n=("error", "count"), heldout_mae=("abs_error", "mean"),
                )
                rankings.append(ranking.merge(quality, on="municipality_id", how="left", validate="one_to_one"))
                for p in panel_eval(ranking, test_counts, level, np.random.default_rng(20261123)):
                    p["window"] = window["name"]
                    panels.append(p)
            national = ranks["national"].set_index("municipality_id").weight.reindex(munis).fillna(1).to_numpy(float)
            canton = ranks["canton"].set_index("municipality_id").weight.reindex(munis).fillna(1).to_numpy(float)
            national_panel = ranks["national"].query("eligible").sort_values(
                ["mae", "municipality_id"]
            ).head(20).municipality_id.astype(str).to_numpy()
            panel_idx = pd.Index(munis).get_indexer(national_panel)
            if len(panel_idx) != 20 or (panel_idx < 0).any():
                raise ValueError("National panel does not match train geography")
        for name in SUITES[suite]:
            pca, targets = fold["pca"], fold["heads"]
            predicted_heads = original.copy()
            ess = float(nt)
            with threadpool_limits(limits=2):
                if name.startswith("local_weight"):
                    h = int(name.removeprefix("local_weight"))
                    w = recency_weights(train_dates, window["start"], h)
                    predicted_heads[:, 1:] = fit_heads(proto, fold["train_x"], targets[:, 1:], fold["val_x"], w)
                    ess = effective_n(w)
                elif name.startswith("local_pca"):
                    h = int(name.removeprefix("local_pca").removeprefix("_only"))
                    w = recency_weights(train_dates, window["start"], h)
                    pca, targets = metric_basis(residuals, mu, w, municipal_uniform,
                                               params["dimensions"], params["random_state"])
                    local_weights = None if "_only" in name else w
                    predicted_heads[:, 1:] = fit_heads(proto, fold["train_x"], targets[:, 1:], fold["val_x"], local_weights)
                    ess = float(nt) if local_weights is None else effective_n(w)
                elif name.startswith("similarity_xgb"):
                    effective = []
                    for j in range(nv):
                        recent = recency_weights(train_dates, window["start"], 10) if name.endswith("recent10") else None
                        w = similarity_sample_weights(sim[j], recent)
                        predicted_heads[j:j+1, 1:] = fit_heads(
                            proto, fold["train_x"], targets[:, 1:], fold["val_x"][j:j+1], w
                        )
                        effective.append(effective_n(w))
                    ess = float(np.mean(effective))
                elif name == "analog_blend25":
                    analog = np.stack([np.average(targets[:, 1:], axis=0, weights=similarity_sample_weights(s))
                                       for s in sim])
                    predicted_heads[:, 1:] = 0.75 * original[:, 1:] + 0.25 * analog
                elif name in ("national_basis", "cantonal_basis", "combined_basis"):
                    cw = national if name == "national_basis" else canton if name == "cantonal_basis" else np.sqrt(national * canton)
                    cw = cw / cw.mean()
                    pca, targets = metric_basis(residuals, mu, uniform, cw,
                                               params["dimensions"], params["random_state"])
                    predicted_heads[:, 1:] = fit_heads(proto, fold["train_x"], targets[:, 1:], fold["val_x"])
                elif name == "national_panel_head":
                    # The head predicts the representative panel's historical
                    # equal-commune mean. Recover the level by subtracting the
                    # predicted panel residual; no held-out panel outcome enters.
                    actual_panel = residuals[:, panel_idx]
                    count = np.isfinite(actual_panel).sum(axis=1)
                    panel_delta = np.divide(np.nansum(actual_panel, axis=1), count,
                                            out=np.zeros(nt), where=count > 0)
                    panel_targets = (mu + panel_delta)[:, None]
                    panel_prediction = fit_heads(proto, fold["train_x"], panel_targets, fold["val_x"])[:, 0]
                    predicted_profiles = pca.mean_[None, :] + predicted_heads[:, 1:] @ pca.components_
                    predicted_heads[:, 0] = panel_prediction - predicted_profiles[:, panel_idx].mean(axis=1)
                elif name not in ("reference", "local_drift25"):
                    raise ValueError(f"Unknown configuration {name}")
            if name == "local_drift25":
                va = add_local_adjustment(base_prediction, fold, 0.25 * local_drift(residuals, train_dates, val_dates))
            else:
                va = reconstruct(predicted_heads, pca, fold["val_idx"], fold["val_muni"])
            adjusted = anchor_fast(va, groups)
            structural, _ = diagnostics(fold["val_y"], va, fold["val_idx"], nv)
            anchored, per = diagnostics(fold["val_y"], adjusted, fold["val_idx"], nv)
            row = {"configuration": name, "window": window["name"], "validation_objects": nv,
                   "effective_local_train": ess, **{"structural_" + k: v for k, v in structural.items()},
                   **{"anchored_" + k: v for k, v in anchored.items()}}
            records.append(row)
            for vote, mae in zip(fold["val_ids"], per, strict=True):
                object_rows.append({"variant": name, "vote_id": vote,
                                    "vote_date": str(val_lookup.loc[vote, "vote_date"].date()),
                                    "poll_available": int(val_lookup.loc[vote, "poll_available"]),
                                    "mae_pp": float(mae)})
            print("FOLD", json.dumps(row, allow_nan=False), flush=True)
    detail, objects = pd.DataFrame(records), pd.DataFrame(object_rows)
    summary = []
    for name, g in detail.groupby("configuration", sort=False):
        row = {"configuration": name}
        for c in detail:
            if c.startswith(("structural_", "anchored_")):
                row[c] = float(np.average(g[c], weights=g.validation_objects))
        row["effective_local_train"] = float(g.effective_local_train.mean())
        sub = objects[objects.variant.eq(name)]
        if len(sub) != 66 or sub.vote_id.nunique() != 66 or sub.vote_date.nunique() != 23:
            raise ValueError("Wrong validation population")
        row["with_poll_mae"] = float(sub[sub.poll_available.eq(1)].mae_pp.mean())
        row["without_poll_mae"] = float(sub[sub.poll_available.eq(0)].mae_pp.mean())
        if name != "reference":
            row["gain_interval"] = paired_date_bootstrap(objects, "reference", name)
        summary.append(row)
    baseline = next(r for r in summary if r["configuration"] == "reference")
    if not np.isclose(baseline["anchored_mae"], 7.618292700184025, atol=0.0002, rtol=0):
        raise ValueError("Reference failed")
    detail.to_csv(output / "fold_metrics.csv", index=False)
    objects.to_csv(output / "object_metrics.csv", index=False)
    pd.DataFrame(summary).to_csv(output / "summary.csv", index=False)
    if suite == "representative":
        rank_table, panel_table = pd.concat(rankings, ignore_index=True), pd.DataFrame(panels)
        rank_table.to_csv(output / "representative_ranks.csv", index=False)
        panel_table.to_csv(output / "panel_diagnostics.csv", index=False)
        panel_summary = panel_table.groupby(["level", "k"]).agg(
            cases=("panel_error_pp", "size"), panel_mae=("panel_error_pp", "mean"),
            random_mae=("random_error_pp", "mean"),
        ).reset_index()
        print("PANELS", panel_summary.to_json(orient="records"), flush=True)
        latest = rank_table[(rank_table.level == "national") & (rank_table.window == "2021-2022")
                            & rank_table.eligible].sort_values("mae").head(10)
        print("REPRESENTATIVES", latest[["commune_name", "canton", "mae", "heldout_mae", "coverage"]].to_json(orient="records"), flush=True)
    manifest = {"suite": suite, "status": "complete", "strict_forecast_ready": False,
                "comparison_targets_loaded": False, "plan": plan, "configurations": SUITES[suite],
                "prepared_data_sha256": sha(base / "dataset.parquet"), "code_sha256": sha(Path(__file__)),
                "summary": summary}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    print("SUMMARY", json.dumps(summary, allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--suite", required=True, choices=SUITES)
    args = parser.parse_args()
    run(args.base, args.output, args.suite)


if __name__ == "__main__":
    main()

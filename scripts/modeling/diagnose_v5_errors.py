"""Read-only error analysis of frozen V5 held-out predictions.

The oracle calculations intentionally use observed development outcomes, solely
to diagnose error components. No oracle values are predictive features or new
candidate scores. No 2023+ target rows are read. The historical profile basis is
fitted exclusively on earlier outcomes; coefficients in the oracle are fitted
to each held-out object's observed outcomes, explicitly as hindsight.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from threadpoolctl import threadpool_limits

from scripts.common.config import ROOT
from scripts.integration.build_modeling_dataset import clean_outcomes
from scripts.modeling.semantic_features_v4 import load_annotations
from scripts.modeling.semantic_labels_v5 import build_coarse_table, load_history


def hashfile(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def score_part(y, p):
    """Use shares internally; all returned errors are in percentage points."""
    r = (p - y) * 100
    centered = r - r.mean()
    # Shift is chosen on observed evaluation outcomes. Optimizes MAE over
    # unrestricted uniform offsets only; it is not an attainable forecast.
    median = float(np.median(r))
    ys, ps = y.std(), p.std()
    return {
        "mae": float(np.abs(r).mean()),
        "bias": float(r.mean()),
        "bias_abs": float(abs(r.mean())),
        "oracle_shift_mae": float(np.abs(r - median).mean()),
        "median_bias": median,
        "mse": float(np.mean(r ** 2)),
        "bias_sq": float(r.mean() ** 2),
        "centered_mse": float(np.mean(centered ** 2)),
        "centered_mae": float(np.abs(centered).mean()),
        "local_corr": float(np.corrcoef(y, p)[0, 1]) if ys > 0 and ps > 1e-10 else None,
        "true_sd": float(100 * ys),
        "pred_sd": float(100 * ps),
        "pred_to_true_sd": float(ps / ys) if ys > 0 else None,
    }


def group_summary(df):
    return {"objects": len(df), **{
        k: float(df[k].mean()) for k in [
            "mae", "bias_abs", "oracle_shift_mae", "mse", "bias_sq", "centered_mse",
            "centered_mae", "local_corr", "true_sd", "pred_sd", "pred_to_true_sd",
        ]
    }}


def load_outcomes():
    source = ROOT / "data/processed/ofs-votes/votes_communes.parquet"
    cols = [
        "municipality_id", "vote_id", "vote_key", "vote_date", "canton",
        "votes_yes", "votes_no", "is_special_unit", "is_tiebreak_question",
        "is_provisional", "flag_valid_gt_ballots", "flag_yes_no_gt_valid",
    ]
    ofs = pd.read_parquet(
        source, columns=cols,
        filters=[("vote_date", ">=", pd.Timestamp("1990-01-01")),
                 ("vote_date", "<", pd.Timestamp("2023-01-01"))],
    )
    if ofs.vote_date.ge("2023-01-01").any():
        raise ValueError("Forbidden target dates")
    clean, _ = clean_outcomes(ofs)
    for col in ("vote_id", "municipality_id", "vote_key"):
        clean[col] = clean[col].astype(str)
    return clean


def make_oracles(clean, base):
    """Held-out shape reconstruction with past-only PCA basis and known test y."""
    ranks = (0, 1, 2, 3, 5, 10, 20, 40, 80)
    records = []
    windows = base[["window", "vote_date"]].groupby("window").vote_date.min()
    for window, first in windows.items():
        tr = clean[clean.vote_date.lt(first)]
        m = tr.pivot(index="vote_id", columns="municipality_id", values="yes_share")
        matrix = m.to_numpy(dtype=float)
        means = np.nanmean(matrix, axis=1)
        matrix = np.where(np.isnan(matrix), means[:, None], matrix) - means[:, None]
        # The actual model's five-dimensional basis uses randomized PCA.
        # Full-SVD rank sweep is a diagnostic, not the identical fitted model.
        with threadpool_limits(limits=2):
            pca = PCA(n_components=max(ranks), svd_solver="full").fit(matrix)
        for vote, rows in base[base.window.eq(window)].groupby("vote_id"):
            idx = m.columns.get_indexer(rows.municipality_id.astype(str))
            valid = idx >= 0
            y = rows.yes_share.to_numpy(float)
            historic_mean = np.zeros(len(y))
            historic_mean[valid] = pca.mean_[idx[valid]]
            yy = y - y.mean()
            row = {
                "vote_id": str(vote), "window": window,
                "unknown_municipalities": int((~valid).sum()),
                "constant_oracle_mae": float(np.abs(y - np.median(y)).mean() * 100),
            }
            for rank in ranks:
                basis = np.zeros((len(y), rank))
                basis[valid] = pca.components_[:rank, idx[valid]].T
                if rank:
                    # Use observed centered outcomes solely to select oracle
                    # coefficients, using an intercept for the available communes.
                    design = np.column_stack([np.ones(len(y)), basis])
                    beta = np.linalg.lstsq(design[valid], (yy - historic_mean)[valid], rcond=None)[0]
                    profile = historic_mean + basis @ beta[1:]
                else:
                    profile = historic_mean
                r = (profile - yy) * 100
                row[f"pca_{rank}_oracle_mae"] = float(np.abs(r - np.median(r)).mean())
            records.append(row)
    return pd.DataFrame(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    path, output = args.artifact, args.output
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "complete" or not manifest["reference_reproduced"]:
        raise ValueError("Frozen benchmark not complete")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Choose a clean diagnostic output directory")
    output.mkdir(parents=True, exist_ok=True)

    raw = pd.read_csv(ROOT / "data/processed/municipal_v3/object_features.csv",
                      dtype={"vote_id": str}, usecols=["vote_id", "vote_date"])
    tags = build_coarse_table(raw, load_history(), load_annotations(
        ROOT / "data/annotations/yes_effects_v4.json"))
    metadata = tags[["vote_id", "coarse_documented", "annotation_origin", "coarse_tags"]]
    titles = pd.read_parquet(
        ROOT / "data/processed/swissvotes/swissvotes_clean.parquet",
        columns=["vote_key", "vote_date", "titel_kurz_f", "titel_off_f"],
    )
    titles["vote_key"] = titles.vote_key.astype(str)
    titles = titles.rename(columns={"vote_key": "vote_id"})
    titles["title"] = titles.titel_kurz_f.fillna(titles.titel_off_f)
    titles = titles[["vote_id", "title"]]
    if titles.vote_id.duplicated().any():
        raise ValueError("Duplicated title")
    clean = load_outcomes()
    ofs_keys = clean[["municipality_id", "vote_id", "canton", "votes_yes", "votes_no", "yes_share"]]
    typologies = pd.read_parquet(
        ROOT / "data/processed/typologies/commune_typologies.parquet",
        columns=["municipality_id", "urban_rural", "language_region"],
    )
    typologies["municipality_id"] = typologies.municipality_id.astype(str)
    outcomes, summaries, spatial = [], [], []
    expected = None
    base = None
    for item in manifest["runs"]:
        name = item["variant"]
        file = path / f"{name}_predictions.parquet"
        if hashfile(file) != item["predictions_sha256"]:
            raise ValueError(f"Predictions hash mismatch: {name}")
        frame = pd.read_parquet(file)
        for col in ("vote_id", "municipality_id"):
            frame[col] = frame[col].astype(str)
        frame["vote_date"] = pd.to_datetime(frame.vote_date)
        if len(frame) != 138868 or frame.vote_id.nunique() != 66 or frame.vote_date.nunique() != 23:
            raise ValueError("Wrong development population")
        if frame.vote_date.ge("2023-01-01").any():
            raise ValueError("Forbidden comparison period")
        keys = frame[["vote_id", "municipality_id", "yes_share", "poll_available"]]
        if expected is None:
            expected = keys.copy()
        else:
            pd.testing.assert_frame_equal(expected, keys)
        for vote, rows in frame.groupby("vote_id", sort=False):
            y = rows.yes_share.to_numpy(float)
            structural = rows.structural_prediction.to_numpy(float)
            polled = rows.prediction.to_numpy(float)
            if rows.poll_available.nunique() != 1:
                raise ValueError("Inconsistent poll metadata")
            for kind, prediction in [("structural", structural), ("anchored", polled)]:
                outcomes.append({
                    "variant": name, "kind": kind, "vote_id": vote,
                    "vote_date": rows.vote_date.iloc[0], "window": rows.window.iloc[0],
                    "poll_available": int(rows.poll_available.iloc[0]),
                    "observed_mean": float(y.mean()), "predicted_mean": float(prediction.mean()),
                    "rows": len(rows), **score_part(y, prediction),
                })
        frame = frame.merge(ofs_keys, on=["vote_id", "municipality_id"],
                            how="left", validate="one_to_one", suffixes=("", "_ofs"))
        if frame.votes_yes.isna().any() or not np.allclose(frame.yes_share, frame.yes_share_ofs):
            raise ValueError("OFS row mismatch")
        frame = frame.merge(typologies, on="municipality_id", how="left", validate="many_to_one")
        frame["valid_votes"] = frame.votes_yes + frame.votes_no
        # Size here uses the observed count as a diagnostic, never a predictor.
        frame["valid_votes_group"] = pd.cut(
            frame.valid_votes, [-1, 99, 499, 1999, 9999, float("inf")],
            labels=["<100", "100-499", "500-1999", "2000-9999", "10000+"],
        ).astype(str)
        frame["err"] = (frame.prediction - frame.yes_share) * 100
        frame["abs_err"] = frame.err.abs()
        frame["centered_err"] = frame.err - frame.groupby("vote_id").err.transform("mean")
        frame["abs_centered_err"] = frame.centered_err.abs()
        if name == "baseline_pca5":
            base = frame.copy()
        for column in ["canton", "urban_rural", "language_region", "valid_votes_group"]:
            # Equal-object means within a group, with row count reported separately.
            grouped = frame.groupby([column, "vote_id"], observed=True, dropna=False).agg(
                mae=("abs_err", "mean"), bias=("err", "mean"),
                centered_mae=("abs_centered_err", "mean"), n=("abs_err", "size"),
            ).reset_index()
            for group, g in grouped.groupby(column, observed=True, dropna=False):
                spatial.append({
                    "variant": name, "group_type": column, "group": str(group),
                    "objects": len(g), "rows": int(g.n.sum()), "mae": float(g.mae.mean()),
                    "bias": float(g.bias.mean()), "centered_mae": float(g.centered_mae.mean()),
                })
    detail = pd.DataFrame(outcomes).merge(metadata, on="vote_id", validate="many_to_one")
    detail = detail.merge(titles, on="vote_id", how="left", validate="many_to_one")
    detail.to_csv(output / "objects.csv", index=False)
    spatial = pd.DataFrame(spatial)
    spatial.to_csv(output / "spatial.csv", index=False)
    for (variant, kind), group in detail.groupby(["variant", "kind"]):
        groups = [("all", group), ("polled", group[group.poll_available.eq(1)]),
                  ("unpolled", group[group.poll_available.eq(0)]),
                  ("annotated", group[group.coarse_documented.eq(1)]),
                  ("unannotated", group[group.coarse_documented.eq(0)])]
        for label, g in groups:
            if len(g):
                summaries.append({"variant": variant, "kind": kind,
                                  "subset": label, **group_summary(g)})
    pd.DataFrame(summaries).to_csv(output / "model_summary.csv", index=False)
    base_by_vote = detail[(detail.variant.eq("baseline_pca5")) & (detail.kind.eq("anchored"))]
    if not np.isclose(base_by_vote.mae.mean(), manifest["reference_mae_pp"], atol=1e-10):
        raise ValueError("Reference MAE not reproduced")
    oracle = make_oracles(clean, base)
    oracle.to_csv(output / "pca_oracle.csv", index=False)
    # Report per-object shift and shape changes under identical poll coverage.
    print(pd.DataFrame(summaries).query("variant == 'baseline_pca5'").to_string(index=False))
    print("PCA ORACLE", oracle.select_dtypes("number").mean().to_dict())
    print("All output files generated; these are retrospective diagnostics, not forecasts.")


if __name__ == "__main__":
    main()

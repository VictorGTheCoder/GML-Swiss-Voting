"""V11.1: uncompressed lexical kernels on historical aggregate vote profiles.

Compare structured-only and text-only kernels with a hybrid, plus low-rank
versus full local outcomes. Every transformation and kernel fit uses only
objects before the start of the evaluation fold. No partial current results.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.kernel_ridge import KernelRidge
from sklearn.metrics.pairwise import cosine_similarity, euclidean_distances
from threadpoolctl import threadpool_limits

from scripts.modeling.audit_xgboost_capacity import prepare_fold, reconstruct
from scripts.modeling.enrichment_experiment_v3 import baseline_features
from scripts.modeling.enrichment_v1089 import anchor
from scripts.modeling.ensemble_v1010 import KEYS, read_artifact
from scripts.modeling.expectations_v101 import REFERENCE, multiscale
from scripts.modeling.local_profiles_v7 import historical_matrix, metric_basis
from scripts.modeling.regional_anchor_v8 import shift_to
from scripts.modeling.semantic_poll_comparison_v4 import paired_date_bootstrap, sha
from scripts.modeling.semantic_training_v5 import PLAN
from scripts.modeling.spatial_margins_v81 import contexts
from scripts.modeling.temporal_drift_v6 import recency_weights
from scripts.modeling.turnout_v103 import load_ballots

METRICS = ("mae_pp", "centered_mae_pp", "national_mae_pp", "canton_mae_pp")
BEST = 6.988599997055331
ALPHA = .5
CONFIGS = {
    "structured_rank5": ("structured", False),
    "structured_full": ("structured", True),
    "lexical_rank5": ("lexical", False),
    "lexical_full": ("lexical", True),
    "hybrid_rank5": ("hybrid", False),
    "hybrid_full": ("hybrid", True),
}


def structured_kernel(train, query):
    distance = euclidean_distances(train, squared=True)
    positive = distance[distance > 1e-10]
    scale = float(np.median(positive)) if len(positive) else 1.
    return np.exp(-distance / scale), np.exp(-euclidean_distances(query, train, squared=True) / scale)


def lexical_kernel(train_text, query_text, analyzer):
    vectorizer = TfidfVectorizer(
        analyzer=analyzer, ngram_range=(3, 5) if analyzer == "char_wb" else (1, 2),
        min_df=2, max_features=12000, sublinear_tf=True,
    )
    a = vectorizer.fit_transform(train_text)
    b = vectorizer.transform(query_text)
    return cosine_similarity(a), cosine_similarity(b, a)


def blend_kernels(a, b, fraction):
    return tuple((1 - fraction) * x + fraction * y for x, y in zip(a, b, strict=True))


def centered_krr(train, query, targets, alpha=ALPHA):
    """Kernel and outcome centering, using only training moments."""
    if alpha <= 0 or train.shape != (len(targets), len(targets)) or query.shape[1] != len(targets):
        raise ValueError("Invalid kernel dimensions or penalty")
    col = train.mean(axis=0)
    grand = float(col.mean())
    k = train - train.mean(axis=1, keepdims=True) - col[None, :] + grand
    q = query - query.mean(axis=1, keepdims=True) - col[None, :] + grand
    mean = targets.mean(axis=0)
    model = KernelRidge(alpha=alpha, kernel="precomputed")
    model.fit(k, targets - mean)
    return model.predict(q) + mean


def full_reconstruct(h, object_idx, municipality_idx):
    result = h[object_idx, 0].copy()
    known = municipality_idx >= 0
    result[known] += h[object_idx[known], municipality_idx[known] + 1]
    return np.clip(result, 0., 1.)


def run(base, acquisition, old_acquisition, fusion, frozen, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve earlier experiments")
    m = json.loads((acquisition / "manifest.json").read_text())
    path = acquisition / "text_corpus.parquet"
    if m["status"] != "complete" or m["text_corpus_sha256"] != sha(path):
        raise ValueError("Frozen text source changed")
    corpus = pd.read_parquet(path).set_index("vote_id", verify_integrity=True)
    corpus.index = corpus.index.astype(str)
    corpus["vote_date"] = pd.to_datetime(corpus.vote_date)
    if len(corpus) != 306 or corpus.vote_date.ge("2023-01-01").any():
        raise ValueError("Unexpected text population")
    fixed = read_artifact(frozen, ["reference", "reference_weight", "page_tfidf_16_all"])
    plan = json.loads(PLAN.read_text())
    params = dict(plan["regressor_parameters"])
    numeric, categorical = baseline_features(json.loads((base / "data_manifest.json").read_text()))
    data, cases = contexts(base, old_acquisition, fusion)
    if data.vote_date.ge("2023-01-01").any():
        raise ValueError("Forbidden comparison outcomes")
    data["municipality_id"] = data.municipality_id.astype(str)
    data["vote_id"] = data.vote_id.astype(str)
    case_map = {vote: (day, v, f, lm, um) for vote, day, v, f, lm, um in cases}
    obs = {k: g.set_index("municipality_id", verify_integrity=True) for k, g in load_ballots().groupby("vote_id")}
    records, canton_rows, blocks, diagnostics = [], [], [], []
    with threadpool_limits(limits=2):
        for window in plan["validation_windows"]:
            tr = data[data.vote_date.lt(window["start"])]
            ev = data[data.vote_date.between(window["start"], window["end"])].copy()
            if tr.vote_date.max() >= ev.vote_date.min():
                raise ValueError("Nonchronological fold")
            fold = prepare_fold(tr, ev, numeric, categorical, params)
            ids, queries = fold["train_ids"], fold["val_ids"]
            if not corpus.loc[ids].vote_date.lt(window["start"]).all():
                raise ValueError("Text training cutoff mismatch")
            if not corpus.loc[queries].vote_date.between(window["start"], window["end"]).all():
                raise ValueError("Text evaluation date mismatch")
            _, mu, residuals = historical_matrix(tr, ids)
            dates = tr[["vote_id", "vote_date"]].drop_duplicates().set_index("vote_id").vote_date
            rw = recency_weights(dates.loc[ids], window["start"], 5)
            basis, heads = metric_basis(residuals, mu, rw, np.ones(residuals.shape[1]), 5, params["random_state"])
            full = np.column_stack([mu, np.nan_to_num(residuals, nan=0.)])
            struct = structured_kernel(fold["train_x"], fold["val_x"])
            train_text = corpus.loc[ids, "document_text"]
            query_text = corpus.loc[queries, "document_text"]
            chars = lexical_kernel(train_text, query_text, "char_wb")
            words = lexical_kernel(train_text, query_text, "word")
            lexical = blend_kernels(chars, words, .5)
            kernels = {"structured": struct, "lexical": lexical,
                       "hybrid": blend_kernels(struct, lexical, .5)}
            ordered = ev[["vote_id", "municipality_id"]].copy()
            for name, (kind, use_full) in CONFIGS.items():
                h = centered_krr(*kernels[kind], full if use_full else heads)
                ordered[name] = (full_reconstruct(h, fold["val_idx"], fold["val_muni"]) if use_full
                                 else reconstruct(h, basis, fold["val_idx"], fold["val_muni"]))
            for j, vote in enumerate(queries):
                nearest = int(np.argmax(lexical[1][j]))
                diagnostics.append({"vote_id": vote, "fold": window["name"], "nearest_prior_vote": ids[nearest],
                                    "nearest_similarity": float(lexical[1][j, nearest]),
                                    "train_objects": len(ids), "matched_page": bool(corpus.loc[vote, "usable_summary"])})
            for vote, group in ordered.groupby("vote_id"):
                day, v, f, lm, um = case_map[vote]
                g = group.set_index("municipality_id", verify_integrity=True).reindex(v.municipality_id)
                keys = pd.MultiIndex.from_frame(v[KEYS].assign(vote_id=vote, vote_date=day))
                pinned = fixed.reindex(keys)
                w = v.weight.to_numpy(float)
                ref = pinned.reference.to_numpy(float)
                best = pinned.page_tfidf_16_all.to_numpy(float)
                if not np.isfinite(np.column_stack([ref, best])).all() or not np.allclose(w, pinned.reference_weight):
                    raise ValueError("Frozen prediction alignment mismatch")
                forecasts = {"reference": ref, "v108_tfidf": best}
                for name in CONFIGS:
                    p = anchor(g[name].to_numpy(float), v, f, lm, um)
                    forecasts[name] = p
                    if name.startswith("hybrid"):
                        # Hold V10.8 ex-ante weighted national anchor, test local contrasts.
                        forecasts[name + "_local"] = shift_to(p, w, np.average(best, weights=w))
                forecasts["hybrid_full_blend50"] = .5 * forecasts["hybrid_full"] + .5 * best
                # Access actual ballots for scoring only.
                actual = obs[vote].reindex(v.municipality_id)
                y = v.yes_share.to_numpy(float)
                yes, no = actual.votes_yes.to_numpy(float), actual.votes_no.to_numpy(float)
                block = v[KEYS + ["yes_share"]].copy()
                block["reference_weight"] = w
                for name, p in forecasts.items():
                    met, cs = multiscale(y, p, w, yes, no, actual.canton.astype(str).to_numpy())
                    records.append({"variant": name, "vote_id": vote, "vote_date": str(day.date()),
                                    "fold": window["name"], "domain": str(v.object_domain_1.iloc[0]),
                                    "covered": bool(corpus.loc[vote, "usable_summary"]), **met})
                    canton_rows.extend({"variant": name, "vote_id": vote, **c} for c in cs)
                    block[name] = p
                blocks.append(block)
            print("FOLD", window["name"], "train", len(ids), "test", len(queries), flush=True)
    detail = pd.DataFrame(records)
    summary = []
    for name, g in detail.groupby("variant", sort=False):
        if len(g) != 66 or g.vote_date.nunique() != 23:
            raise ValueError("Incomplete benchmark")
        summary.append({"variant": name, "objects": 66, "covered_objects": int(g.covered.sum()),
                        **{k: float(g[k].mean()) for k in METRICS},
                        "gain_interval": [0., 0.] if name == "reference" else paired_date_bootstrap(detail, "reference", name),
                        "vs_v108_interval": [0., 0.] if name == "v108_tfidf" else paired_date_bootstrap(detail, "v108_tfidf", name)})
    by_name = {s["variant"]: s for s in summary}
    if not np.isclose(by_name["reference"]["mae_pp"], REFERENCE, atol=2e-4, rtol=0):
        raise ValueError("Reference changed")
    if not np.isclose(by_name["v108_tfidf"]["mae_pp"], BEST, atol=2e-4, rtol=0):
        raise ValueError("V10.8 comparator changed")
    predictions = pd.concat(blocks, ignore_index=True)
    if len(predictions) != 138868 or predictions.duplicated(KEYS).any():
        raise ValueError("Prediction population changed")
    output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output / "object_metrics.csv", index=False)
    for column in ("fold", "domain"):
        detail.groupby(["variant", column])[list(METRICS)].agg(["mean", "size"]).to_csv(output / f"{column}_metrics.csv")
    pd.DataFrame(canton_rows).to_csv(output / "canton_metrics.csv", index=False)
    pd.DataFrame(diagnostics).to_csv(output / "nearest_prior_objects.csv", index=False)
    for name in by_name:
        predictions[name + "_absolute_error"] = (predictions[name] - predictions.yes_share).abs() * 100
    errors = [name + "_absolute_error" for name in by_name]
    predictions.groupby("municipality_id")[errors].mean().to_csv(output / "municipality_metrics.csv")
    predictions.drop(columns=errors).to_parquet(output / "predictions.parquet", index=False)
    pd.DataFrame(summary).to_csv(output / "summary.csv", index=False)
    manifest = {"status": "complete", "strict_forecast_ready": False, "comparison_targets_loaded": False,
                "alpha": ALPHA, "configs": CONFIGS, "corpus_sha256": sha(path),
                "prediction_sha256": sha(output / "predictions.parquet"), "summary": summary}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    print("SUMMARY", json.dumps(summary, allow_nan=False), flush=True)
    print("FOLD_MEANS", detail.groupby(["variant", "fold"]).mae_pp.mean().unstack().to_json(), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "acquisition", "old-acquisition", "fusion", "frozen", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    run(a.base, a.acquisition, a.old_acquisition, a.fusion, a.frozen, a.output)


if __name__ == "__main__":
    main()

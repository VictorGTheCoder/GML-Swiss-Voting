"""Strict matched replay: Gradiom versus frozen GML V2 and V10.8 recipe.

Only the seven archived objects shared with the previously exposed V2
comparison period are evaluated. All model training ends before 2023.
V10.8's TF-IDF choice, 16 features and PCA5/XGB hyperparameters were fixed
on the original development population. No post-2022 fit or tuning.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from scripts.common.config import ROOT
from scripts.modeling.audit_xgboost_capacity import ArrayPredictor, anchor_fast, reconstruct
from scripts.modeling.enrichment_experiment_v3 import baseline_features
from scripts.modeling.gradiom_benchmark import V2_SCORES, date_bootstrap, errors
from scripts.modeling.local_profiles_v7 import fit_heads, historical_matrix, metric_basis
from scripts.modeling.municipal_v2 import fit_model, freeze_history, metrics, read_data
from scripts.modeling.object_profile_v2 import ObjectProfileRegressor
from scripts.modeling.poll_anchor import POLL_ADDED_COLUMNS, PollAnchoredRegressor, add_poll_features
from scripts.modeling.remaining_priorities_v9 import text_features
from scripts.modeling.semantic_poll_comparison_v4 import sha
from scripts.modeling.semantic_training_v5 import CURRENT_POLLS, PLAN
from scripts.modeling.temporal_drift_v6 import recency_weights
from scripts.modeling.text_v108 import TEXT_ROOT, pick_pages

FROZEN = ROOT / "experiments/municipal_v2/frozen_selection_20261123.json"
SHARED = tuple(str(k) for k in range(6730, 6800, 10))
MODELS = ("gradiom", "gml_v2_original", "gml_v2_aligned", "gml_recent_pca_aligned",
          "gml_v108_aligned")


def query_corpus(evaluation):
    """Apply V10.8's existing unique question-page match to only the query objects."""
    keys = evaluation[["vote_id", "vote_key", "vote_date"]].drop_duplicates().copy()
    keys["vote_id"] = keys.vote_id.astype(str)
    keys["vote_key"] = keys.vote_key.astype(str)
    if set(keys.vote_id) != set(SHARED) or keys.vote_id.duplicated().any():
        raise ValueError("Wrong comparison objects")
    sv = pd.read_parquet(ROOT / "data/processed/swissvotes/swissvotes_clean.parquet",
                         columns=["vote_key", "vote_date", "titel_kurz_f", "titel_off_f"])
    sv["vote_key"] = sv.vote_key.astype(str)
    sv["vote_date"] = pd.to_datetime(sv.vote_date)
    roster = keys.merge(sv, on=["vote_key", "vote_date"], validate="one_to_one")
    if len(roster) != len(keys):
        raise ValueError("Missing query title")
    sources = pd.read_parquet(TEXT_ROOT / "sources.parquet",
                              columns=["source_id", "pdf_sha256", "vote_date", "official_url", "language"])
    sources["vote_date"] = pd.to_datetime(sources.vote_date)
    sources = sources[sources.language.eq("fr")
                      & sources.official_url.str.match(r"^https://(?:www\.)?bk\.admin\.ch/", na=False)]
    pages = pd.read_parquet(TEXT_ROOT / "pages.parquet",
                            columns=["source_id", "pdf_sha256", "page_number", "text", "method", "status"])
    objects = pd.read_parquet(TEXT_ROOT / "objects.parquet",
                              columns=["vote_id", "vote_date", "source_id", "pdf_sha256"])
    objects["vote_id"] = objects.vote_id.astype(str)
    objects["vote_date"] = pd.to_datetime(objects.vote_date)
    roster = roster.merge(objects, on=["vote_id", "vote_date"], how="left", validate="one_to_one")
    rows, evidence = [], []
    for day, group in roster.groupby("vote_date"):
        approved = {}
        found = sources[sources.vote_date.eq(day)]
        if len(found) == 1:
            s = found.iloc[0]
            eligible = group[group.source_id.eq(s.source_id) & group.pdf_sha256.eq(s.pdf_sha256)]
            titles = {str(r.vote_id): [str(x) for x in (r.titel_off_f, r.titel_kurz_f) if pd.notna(x)]
                      for r in group.itertuples()}
            p = pages[pages.source_id.eq(s.source_id) & pages.pdf_sha256.eq(s.pdf_sha256) & pages.text.notna()]
            if p.page_number.duplicated().any():
                raise ValueError("Ambiguous page numbers")
            approved = {k: x for k, x in pick_pages(p.to_dict("records"), titles).items()
                        if k in set(eligible.vote_id)}
        for r in group.itertuples():
            title = str(r.titel_off_f if pd.notna(r.titel_off_f) else r.titel_kurz_f)
            x = approved.get(r.vote_id)
            rows.append({"vote_id": str(r.vote_id), "vote_date": day, "title_text": title,
                         "document_text": title + "\n" + x["text"] if x else title,
                         "usable_summary": bool(x)})
            if x:
                evidence.append({"vote_id": str(r.vote_id), "page": int(x["page"]),
                                 "score": float(x["score"]), "source_id": r.source_id,
                                 "pdf_sha256": r.pdf_sha256, "source_url": str(found.iloc[0].official_url)})
    return pd.DataFrame(rows), evidence


def aligned_poll_inputs(frame, dates):
    """Use the printed Gradiom generation day, not any later poll publication."""
    q = frame.drop(columns=POLL_ADDED_COLUMNS, errors="ignore").copy()
    # The exact generation time isn't published. Both source waves are dated
    # that day; use end-of-day Zurich, with the same-day ambiguity disclosed.
    cutoff = pd.to_datetime(q.vote_id.astype(str).map(dates)).dt.tz_localize("Europe/Zurich")
    q["feature_cutoff"] = cutoff + pd.Timedelta(hours=23, minutes=59, seconds=59)
    polls = pd.read_csv(CURRENT_POLLS, dtype={"vote_key": str})
    polls = polls[polls.vote_key.isin(SHARED)]
    return add_poll_features(q, polls)


def national_groups(train, evaluation, params):
    adapter = PollAnchoredRegressor(ArrayPredictor(np.full(len(evaluation), .5)), **params).fit(train)
    details = adapter.predict_components(evaluation)
    weights = adapter._weights(evaluation.reset_index(drop=True)).fillna(0).to_numpy(float)
    result = []
    for positions in evaluation.reset_index(drop=True).groupby("vote_key", sort=False).indices.values():
        pos = np.asarray(positions, dtype=int)
        if bool(details.poll_applied.iloc[pos[0]]):
            w = weights[pos]
            result.append((pos, w / w.sum(), float(details.national_target_mean.iloc[pos[0]])))
    return result


def profile_replay(train, evaluation, manifest, historical_corpus, query):
    """Same past-only PCA, preprocessing and TF-IDF recipe as V10.8."""
    plan = json.loads(PLAN.read_text())
    numeric, categorical = baseline_features(manifest)
    params = dict(plan["regressor_parameters"])
    proto = ObjectProfileRegressor(numeric, categorical, **params)
    proto._validate_feature_lists()
    train_obj, _, _ = proto._object_table(train)
    eval_obj, eval_votes, eval_munis = proto._object_table(evaluation)
    ids, queries = train_obj.index.astype(str).tolist(), eval_obj.index.astype(str).tolist()
    munis, mu, residuals = historical_matrix(train, ids)
    dates = train[["vote_id", "vote_date"]].drop_duplicates().set_index("vote_id").vote_date
    rw = recency_weights(dates.loc[ids], "2023-01-01", 5)
    basis, heads = metric_basis(residuals, mu, rw, np.ones(len(munis)), 5, params["random_state"])
    prep = proto._make_preprocessor()
    tx = prep.fit_transform(train_obj)
    vx = prep.transform(eval_obj)
    corpus = pd.concat([historical_corpus, query], ignore_index=True).set_index("vote_id", verify_integrity=True)
    a, b = text_features(corpus, ids, queries, "tfidf_document", 16)
    object_indices = eval_obj.index.get_indexer(eval_votes)
    municipality_indices = pd.Index(munis).get_indexer(eval_munis)
    if (object_indices < 0).any():
        raise ValueError("Invalid evaluation index")
    plain = fit_heads(proto, tx, heads, vx)
    text = fit_heads(proto, np.column_stack([tx, a]), heads, np.column_stack([vx, b]))
    groups = national_groups(train, evaluation, plan["frozen_poll_parameters"])
    # The V8.1 regional/settlement sources cover 2021--22, not these objects.
    # The existing published fallback is a national-only anchor; no invented
    # margins, no fitted regional targets from the actual outcomes.
    return (anchor_fast(reconstruct(plain, basis, object_indices, municipality_indices), groups),
            anchor_fast(reconstruct(text, basis, object_indices, municipality_indices), groups),
            len(groups))


def paired_metrics(external, gml):
    keys = ["vote_id", "municipality_id"]
    if external.duplicated(keys).any() or gml.duplicated(keys).any():
        raise ValueError("Duplicate matched key")
    paired = external.merge(gml, on=keys, how="inner", validate="one_to_one",
                            suffixes=("", "_gml"))
    if not len(paired) or len(paired) != len(external):
        raise ValueError("Some unchanged archive communes missing from GML")
    if not pd.to_datetime(paired.vote_date).eq(pd.to_datetime(paired.vote_date_gml)).all():
        raise ValueError("Vote date mismatch")
    paired["gradiom"] = paired.gradiom_prediction
    detail = []
    for (vote, day), frame in paired.groupby(["vote_id", "vote_date"]):
        y = frame.official_yes_share.to_numpy(float) * 100
        for method in MODELS:
            p = frame[method].to_numpy(float) * 100
            if not np.isfinite(p).all() or (p < 0).any() or (p > 100).any():
                raise ValueError("Invalid prediction")
            detail.append({"vote_id": vote, "vote_date": day, "variant": method,
                           "communes": len(frame), **errors(p, y)})
    d = pd.DataFrame(detail)
    ref = d[d.variant.eq("gradiom")][["vote_id", "mae_pp"]].set_index("vote_id").mae_pp
    results = []
    for method, group in d.groupby("variant", sort=False):
        g = group.copy()
        g["gain"] = g.vote_id.map(ref) - g.mae_pp
        results.append({"variant": method, "objects": len(g), "rows": int(g.communes.sum()),
                        "mae_pp": float(g.mae_pp.mean()),
                        "centered_mae_pp": float(g.centered_mae_pp.mean()),
                        "bias_pp": float(g.bias_pp.mean()),
                        "gain_vs_gradiom": float(g.gain.mean()),
                        "gain_interval_descriptive": date_bootstrap(g, "gain")})
    return paired, d, results


def run(base, archive, corpus_dir, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve existing comparison")
    # Reproduce already exposed V2 predictions without any new tuning.
    config = json.loads(FROZEN.read_text())["configuration"]
    data, manifest = read_data(base)
    data["vote_id"] = data.vote_id.astype(str)
    data["municipality_id"] = data.municipality_id.astype(str)
    train = data[data.vote_date.between("1990-01-01", "2022-12-31")].copy()
    evaluation = data[data.vote_date.between("2023-01-01", "2025-12-31")].copy()
    if train.vote_id.nunique() != 306 or len(evaluation) != 37890:
        raise ValueError("Wrong frozen V2 population")
    evaluation = freeze_history(train, evaluation)
    observed = evaluation[["vote_id", "municipality_id", "vote_date", "yes_share"]].copy()
    evaluation = evaluation.drop(columns="yes_share")
    archive_detail = pd.read_csv(archive / "object_metrics.csv", dtype={"vote_id": str})
    dates = archive_detail.set_index("vote_id").generated.to_dict()
    query = evaluation[evaluation.vote_id.isin(SHARED)].copy()
    # Freeze corpus bytes from actual V10.8 acquisition artifact.
    corpus_manifest = json.loads((corpus_dir / "manifest.json").read_text())
    path = corpus_dir / "text_corpus.parquet"
    if corpus_manifest["status"] != "complete" or sha(path) != corpus_manifest["text_corpus_sha256"]:
        raise ValueError("V10.8 corpus changed")
    corpus = pd.read_parquet(path)
    corpus["vote_id"] = corpus.vote_id.astype(str)
    if len(corpus) != 306 or pd.to_datetime(corpus.vote_date).ge("2023-01-01").any():
        raise ValueError("Unexpected training corpus")
    docs, evidence = query_corpus(query)
    aligned, poll_audit = aligned_poll_inputs(query, dates)
    with threadpool_limits(limits=2):
        model = fit_model(train, config, manifest)
        all_preds = model.predict(evaluation)
        fixed = observed.copy()
        fixed["prediction"] = all_preds
        _, old_scores, _ = metrics(fixed)
        old = pd.read_csv(V2_SCORES, dtype={"vote_id": str})[["vote_id", "mae_pp"]]
        check = old_scores.merge(old, on="vote_id", suffixes=("_replayed", "_recorded"), validate="one_to_one")
        if len(check) != 18 or not np.allclose(check.mae_pp_replayed, check.mae_pp_recorded, atol=.0002, rtol=0):
            raise ValueError(f"Frozen V2 comparison replay mismatch: {check.to_dict('records')}")
        recent, text, n_anchors = profile_replay(train, aligned, manifest, corpus, docs)
        local = aligned[["vote_id", "municipality_id", "vote_date"]].copy()
        local["gml_v2_aligned"] = model.predict(aligned)
        local["gml_recent_pca_aligned"] = recent
        local["gml_v108_aligned"] = text
        local = local.merge(fixed[["vote_id", "municipality_id", "prediction", "yes_share"]],
                            on=["vote_id", "municipality_id"], validate="one_to_one")
        local = local.rename(columns={"prediction": "gml_v2_original", "yes_share": "repo_yes_share"})
    external = pd.read_parquet(archive / "matched_rows.parquet")
    external["vote_id"] = external.vote_id.astype(str)
    external["municipality_id"] = external.municipality_id.astype(str)
    external = external[external.vote_id.isin(SHARED)]
    if set(external.vote_id) != set(SHARED):
        raise ValueError("Missing shared Gradiom objects")
    paired, detail, results = paired_metrics(external, local)
    if any(r["objects"] != 7 for r in results):
        raise ValueError("Incomplete paired comparison")
    output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output / "paired_object_metrics.csv", index=False)
    pd.DataFrame(results).to_csv(output / "paired_summary.csv", index=False)
    pd.DataFrame(evidence).to_csv(output / "query_page_evidence.csv", index=False)
    result = {"status": "complete", "strict_forecast_ready": False,
              "comparison_is_independent": False, "training_objects": 306, "evaluation_objects": 7,
              "evaluation_dates": int(external.vote_date.nunique()), "matched_rows": len(paired),
              "v2_replay_max_error_pp": float((check.mae_pp_replayed-check.mae_pp_recorded).abs().max()),
              "query_pages_matched": len(evidence), "national_anchors": n_anchors,
              "same_day_publication_time_unknown": True,
              "regional_margin_fallback": "national only; current reviewed regional margins unavailable",
              "observed_revisions_rows": int((paired.official_yes_share-paired.repo_yes_share).abs().gt(1e-8).sum()),
              "poll_selection": poll_audit["selection"],
              "archive_matched_sha256": sha(archive / "matched_rows.parquet"),
              "historical_corpus_sha256": sha(path), "summary": results}
    (output / "manifest.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    print("PAIRED", json.dumps(result, allow_nan=False), flush=True)
    print("OBJECTS", detail.to_json(orient="records"), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "archive", "corpus", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    run(a.base, a.archive, a.corpus, a.output)


if __name__ == "__main__":
    main()

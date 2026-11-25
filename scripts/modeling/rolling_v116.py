"""V11.6: date-wise local refit, with frozen national anchors."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from scripts.modeling.audit_xgboost_capacity import prepare_fold, reconstruct
from scripts.modeling.documentary_audit_v112 import audited_documents, variant_corpus
from scripts.modeling.enrichment_experiment_v3 import baseline_features
from scripts.modeling.enrichment_v1089 import anchor
from scripts.modeling.ensemble_v1010 import KEYS, read_artifact
from scripts.modeling.expectations_v101 import REFERENCE, multiscale
from scripts.modeling.local_profiles_v7 import fit_heads, historical_matrix, metric_basis
from scripts.modeling.object_profile_v2 import ObjectProfileRegressor
from scripts.modeling.procedure_v113 import INSTITUTION, RAW, SOURCE, encode_extra, match_procedure
from scripts.modeling.remaining_priorities_v9 import text_features
from scripts.modeling.semantic_poll_comparison_v4 import paired_date_bootstrap, sha
from scripts.modeling.semantic_training_v5 import PLAN
from scripts.modeling.spatial_margins_v81 import contexts
from scripts.modeling.temporal_drift_v6 import recency_weights
from scripts.modeling.turnout_v103 import load_ballots

METRICS = ("mae_pp", "centered_mae_pp", "national_mae_pp", "canton_mae_pp")
BEST = 6.955753873756506
CONFIGS = {"rolling_text": (True, []), "rolling_institution": (True, INSTITUTION)}


def date_windows(dates):
    days = pd.DatetimeIndex(pd.to_datetime(dates)).unique().sort_values()
    if days.isna().any() or (days >= pd.Timestamp("2023-01-01")).any():
        raise ValueError("Forbidden evaluation date")
    return [{"name": str(day.date()), "start": str(day.date()), "end": str(day.date())}
            for day in days]


def split_date(data, day):
    cutoff = pd.Timestamp(day)
    return data[data.vote_date.lt(cutoff)], data[data.vote_date.eq(cutoff)].copy()


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
    audit, evidence = audited_documents(corpus, m)
    doc = variant_corpus(audit, "original_text")
    fixed = read_artifact(frozen, ["reference", "reference_weight", "v108_tfidf", "institution_text"])
    plan = json.loads(PLAN.read_text())
    params = dict(plan["regressor_parameters"])
    numeric, categorical = baseline_features(json.loads((base / "data_manifest.json").read_text()))
    data, cases = contexts(base, old_acquisition, fusion)
    if data.vote_date.ge("2023-01-01").any():
        raise ValueError("Forbidden comparison outcomes")
    data["municipality_id"] = data.municipality_id.astype(str)
    data["vote_id"] = data.vote_id.astype(str)
    source = pd.read_parquet(SOURCE, columns=RAW, filters=[("vote_date", "<", pd.Timestamp("2023-01-01"))])
    extra = match_procedure(data, source)
    source_coverage = {c: int(extra[c].notna().sum()) for c in extra}
    selection = []
    print("SOURCE_COVERAGE", json.dumps(source_coverage), flush=True)
    case_map = {vote: (day, v, f, lm, um) for vote, day, v, f, lm, um in cases}
    obs = {k: g.set_index("municipality_id", verify_integrity=True) for k, g in load_ballots().groupby("vote_id")}
    records, canton_rows, blocks = [], [], []
    with threadpool_limits(limits=2):
        for window in date_windows([case[1] for case in cases]):
            tr, ev = split_date(data, window["start"])
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
            proto = ObjectProfileRegressor(numeric, categorical, **params)
            ordered = ev[["vote_id", "municipality_id"]].copy()
            a, b = text_features(doc, ids, queries, "tfidf_document", 16)
            extra_train, extra_query = extra.loc[ids], extra.loc[queries]
            for name, (use_text, cols) in CONFIGS.items():
                chosen, rejected = cols, {}
                x, z = encode_extra(extra_train, extra_query, chosen)
                tx, vx = fold["train_x"], fold["val_x"]
                if use_text:
                    tx, vx = np.column_stack([tx, a]), np.column_stack([vx, b])
                h = fit_heads(proto, np.column_stack([tx, x]), heads,
                              np.column_stack([vx, z]))
                ordered[name] = reconstruct(h, basis, fold["val_idx"], fold["val_muni"])
                selection.append({"fold": window["name"], "variant": name, "retained": chosen,
                                  "rejected": rejected, "train_coverage": extra_train[cols].notna().sum().to_dict(),
                                  "eval_coverage": extra_query[cols].notna().sum().to_dict()})
            for vote, group in ordered.groupby("vote_id"):
                day, v, f, lm, um = case_map[vote]
                g = group.set_index("municipality_id", verify_integrity=True).reindex(v.municipality_id)
                keys = pd.MultiIndex.from_frame(v[KEYS].assign(vote_id=vote, vote_date=day))
                pinned = fixed.reindex(keys)
                w = v.weight.to_numpy(float)
                ref = pinned.reference.to_numpy(float)
                best = pinned.institution_text.to_numpy(float)
                previous = pinned.v108_tfidf.to_numpy(float)
                if not np.isfinite(np.column_stack([ref, best, previous])).all() or not np.allclose(w, pinned.reference_weight):
                    raise ValueError("Frozen prediction alignment mismatch")
                forecasts = {"reference": ref, "v108_tfidf": previous, "v113_institution": best}
                for name in CONFIGS:
                    forecasts[name] = anchor(g[name].to_numpy(float), v, f, lm, um)
                # Access actual ballots for scoring only.
                actual = obs[vote].reindex(v.municipality_id)
                y = v.yes_share.to_numpy(float)
                yes, no = actual.votes_yes.to_numpy(float), actual.votes_no.to_numpy(float)
                block = v[KEYS + ["yes_share"]].copy()
                block["reference_weight"] = w
                for name, p in forecasts.items():
                    cols = CONFIGS.get(name, (True, []))[1]
                    covered = bool(extra.loc[vote, cols].notna().any()) if cols else bool(doc.loc[vote, "usable_summary"])
                    met, cs = multiscale(y, p, w, yes, no, actual.canton.astype(str).to_numpy())
                    records.append({"variant": name, "vote_id": vote, "vote_date": str(day.date()),
                                    "fold": window["name"], "domain": str(v.object_domain_1.iloc[0]),
                                    "covered": covered, **met})
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
                        "vs_v113_interval": [0., 0.] if name == "v113_institution" else paired_date_bootstrap(detail, "v113_institution", name)})
    by_name = {s["variant"]: s for s in summary}
    if not np.isclose(by_name["reference"]["mae_pp"], REFERENCE, atol=2e-4, rtol=0):
        raise ValueError("Reference changed")
    if not np.isclose(by_name["v108_tfidf"]["mae_pp"], 6.988599997055331, atol=2e-4, rtol=0):
        raise ValueError("V10.8 comparator changed")
    if not np.isclose(by_name["v113_institution"]["mae_pp"], BEST, atol=2e-4, rtol=0):
        raise ValueError("V11.3 comparator changed")
    predictions = pd.concat(blocks, ignore_index=True)
    if len(predictions) != 138868 or predictions.duplicated(KEYS).any():
        raise ValueError("Prediction population changed")
    output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output / "object_metrics.csv", index=False)
    for column in ("fold", "domain"):
        detail.groupby(["variant", column])[list(METRICS)].agg(["mean", "size"]).to_csv(output / f"{column}_metrics.csv")
    pd.DataFrame(canton_rows).to_csv(output / "canton_metrics.csv", index=False)
    evidence.to_csv(output / "document_evidence.csv", index=False)
    audit.drop(columns=["original_text", "exact_text", "multi_text", "question_text",
                        "mechanism_text"]).to_csv(output / "audit_roster.csv")
    coverage = {s["variant"]: s["covered_objects"] for s in summary}
    (output / "coverage.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    (output / "selection.json").write_text(json.dumps(selection, indent=2), encoding="utf-8")
    extra.reset_index().to_csv(output / "procedure_features.csv", index=False)
    for name in by_name:
        predictions[name + "_absolute_error"] = (predictions[name] - predictions.yes_share).abs() * 100
    errors = [name + "_absolute_error" for name in by_name]
    predictions.groupby("municipality_id")[errors].mean().to_csv(output / "municipality_metrics.csv")
    predictions.drop(columns=errors).to_parquet(output / "predictions.parquet", index=False)
    pd.DataFrame(summary).to_csv(output / "summary.csv", index=False)
    manifest = {"status": "complete", "strict_forecast_ready": False, "comparison_targets_loaded": False,
                "configs": CONFIGS, "coverage": coverage, "corpus_sha256": sha(path),
                "procedure_source_sha256": sha(SOURCE), "source_coverage": source_coverage,
                "selection": selection,
                "evidence_sha256": sha(output / "document_evidence.csv"),
                "prediction_sha256": sha(output / "predictions.parquet"), "summary": summary}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    print("SUMMARY", json.dumps(summary, allow_nan=False), flush=True)
    print("FOLD_MEANS", detail.groupby(["variant", "fold"]).mae_pp.mean().unstack().to_json(), flush=True)
    print("DOMAIN_MEANS", detail.groupby(["variant", "domain"]).mae_pp.mean().unstack().to_json(), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "acquisition", "old-acquisition", "fusion", "frozen", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    run(a.base, a.acquisition, a.old_acquisition, a.fusion, a.frozen, a.output)


if __name__ == "__main__":
    main()

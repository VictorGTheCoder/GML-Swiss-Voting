"""V11.3: procedure and institutional disagreement ablations of V10.8."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from scripts.common.config import ROOT
from scripts.modeling.audit_xgboost_capacity import prepare_fold, reconstruct
from scripts.modeling.documentary_audit_v112 import audited_documents, variant_corpus
from scripts.modeling.enrichment_experiment_v3 import baseline_features
from scripts.modeling.enrichment_v1089 import anchor
from scripts.modeling.ensemble_v1010 import KEYS, read_artifact
from scripts.modeling.expectations_v101 import REFERENCE, multiscale
from scripts.modeling.local_profiles_v7 import fit_heads, historical_matrix, metric_basis
from scripts.modeling.object_profile_v2 import ObjectProfileRegressor
from scripts.modeling.remaining_priorities_v9 import text_features
from scripts.modeling.semantic_poll_comparison_v4 import paired_date_bootstrap, sha
from scripts.modeling.semantic_training_v5 import PLAN
from scripts.modeling.spatial_margins_v81 import contexts
from scripts.modeling.temporal_drift_v6 import recency_weights
from scripts.modeling.turnout_v103 import load_ballots

METRICS = ("mae_pp", "centered_mae_pp", "national_mae_pp", "canton_mae_pp")
BEST = 6.988599997055331
SOURCE = ROOT / "data/processed/swissvotes/swissvotes_clean.parquet"
RAW = ["vote_key", "vote_date", "dat-message", "dat-parl", "pa-iv", "nrja", "nrnein", "srja", "srnein"]
TIMING = ["message_to_parliament_logdays", "parliament_to_vote_logdays"]
INSTITUTION = ["parliamentary_initiative", "chamber_share_gap", "nr_binary_seat_fraction",
               "sr_binary_seat_fraction"]
CONFIGS = {
    "original_replay": (True, []),
    "timing_text": (True, TIMING),
    "institution_text": (True, INSTITUTION),
    "all_text": (True, TIMING + INSTITUTION),
    "all_structured": (False, TIMING + INSTITUTION),
    "pruned_text": (True, TIMING + INSTITUTION),
}


def parse_date(values):
    s = values.astype("string").str.strip()
    a = pd.to_datetime(s, format="%d.%m.%Y", errors="coerce")
    b = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    return a.fillna(b)


def procedural_features(raw):
    if raw.vote_key.duplicated().any():
        raise ValueError("Duplicate Swissvotes key")
    day = pd.to_datetime(raw.vote_date)
    if day.ge("2023-01-01").any():
        raise ValueError("Forbidden comparison period")
    message = parse_date(raw["dat-message"])
    parliament = parse_date(raw["dat-parl"])
    known_parl = parliament.lt(day)
    known_msg = message.le(parliament) & known_parl
    pa = pd.to_numeric(raw["pa-iv"], errors="coerce").astype(float)
    pa = pa.where(pa.isin([0, 1]) & known_parl)
    result = raw[["vote_key", "vote_date"]].copy()
    result["vote_key"] = result.vote_key.astype(str)
    result["message_to_parliament_logdays"] = np.log1p(
        (parliament - message).dt.days.where(known_msg & pa.eq(0)))
    result["parliament_to_vote_logdays"] = np.log1p((day - parliament).dt.days.where(known_parl))
    result["parliamentary_initiative"] = pa
    shares = {}
    for chamber, seats in (("nr", 200), ("sr", 46)):
        yes = pd.to_numeric(raw[chamber + "ja"], errors="coerce").astype(float)
        no = pd.to_numeric(raw[chamber + "nein"], errors="coerce").astype(float)
        total = yes + no
        valid = known_parl & yes.ge(0) & no.ge(0) & total.gt(0) & total.le(seats)
        shares[chamber] = (yes / total.where(valid)).where(valid)
        result[chamber + "_binary_seat_fraction"] = (total / seats).where(valid)
    result["chamber_share_gap"] = (shares["nr"] - shares["sr"]).abs()
    return result


def match_procedure(data, source):
    keys = data[["vote_id", "vote_key", "vote_date"]].drop_duplicates().copy()
    keys["vote_key"] = keys.vote_key.astype(str)
    keys["vote_id"] = keys.vote_id.astype(str)
    if keys.vote_id.duplicated().any() or keys.vote_key.duplicated().any():
        raise ValueError("Invalid modeling object keys")
    p = procedural_features(source)
    out = keys.merge(p, on=["vote_key", "vote_date"], validate="one_to_one", how="left", indicator=True)
    if not out["_merge"].eq("both").all():
        raise ValueError("Procedure source key/date mismatch")
    return out.set_index("vote_id")[TIMING + INSTITUTION]


def select_extra(train, baseline, columns, threshold=.95):
    """Training-only redundancy, pairwise complete numeric observations."""
    keep, rejected = [], {}
    for c in columns:
        s = train[c]
        if s.notna().sum() < 12 or s.nunique(dropna=True) < 2:
            rejected[c] = "low_support_or_constant"
            continue
        others = pd.concat([baseline, train[keep]], axis=1)
        corr = others.corrwith(s, method="spearman").abs()
        support = others.notna().mul(s.notna(), axis=0).sum()
        corr = corr[support.ge(12)].dropna()
        if not corr.empty and corr.max() >= threshold:
            rejected[c] = str(corr.idxmax())
        else:
            keep.append(c)
    return keep, rejected


def encode_extra(train, query, columns):
    a, b = train[columns].to_numpy(float), query[columns].to_numpy(float)
    return np.column_stack([a, np.isnan(a)]), np.column_stack([b, np.isnan(b)])


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
    fixed = read_artifact(frozen, ["reference", "reference_weight", "page_tfidf_16_all"])
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
            proto = ObjectProfileRegressor(numeric, categorical, **params)
            ordered = ev[["vote_id", "municipality_id"]].copy()
            a, b = text_features(doc, ids, queries, "tfidf_document", 16)
            extra_train, extra_query = extra.loc[ids], extra.loc[queries]
            raw_base = tr[["vote_id", *numeric]].drop_duplicates("vote_id").set_index("vote_id").loc[ids]
            raw_base = raw_base.apply(pd.to_numeric, errors="coerce").astype(float)
            for name, (use_text, cols) in CONFIGS.items():
                chosen, rejected = (select_extra(extra_train, raw_base, cols)
                                    if name == "pruned_text" else (cols, {}))
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
                best = pinned.page_tfidf_16_all.to_numpy(float)
                if not np.isfinite(np.column_stack([ref, best])).all() or not np.allclose(w, pinned.reference_weight):
                    raise ValueError("Frozen prediction alignment mismatch")
                forecasts = {"reference": ref, "v108_tfidf": best}
                for name in CONFIGS:
                    forecasts[name] = anchor(g[name].to_numpy(float), v, f, lm, um)
                if not np.allclose(forecasts["original_replay"], best, atol=2e-6, rtol=0):
                    raise ValueError("V10.8 replay differs from frozen predictions")
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

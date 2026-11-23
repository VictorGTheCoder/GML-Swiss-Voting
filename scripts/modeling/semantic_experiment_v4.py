"""Chronological and target-blind ablations for Swissvotes topics and direct YES effects.

Run against a fresh V2 prepared dataset and the versioned V3 object metadata.
All 2023+ objects and their targets are excluded before the model input table is
loaded. Scores are exploratory development results, NOT an independent test.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from scripts.common.config import ROOT
from scripts.modeling.enrichment_experiment_v3 import baseline_features
from scripts.modeling.municipal_v2 import metrics
from scripts.modeling.object_enrichment_v3 import encode_domains, fit_domain_vocabulary
from scripts.modeling.object_profile_v2 import ObjectProfileRegressor
from scripts.modeling.semantic_features_v4 import (
    build_semantic_table, build_topic_table, encode_multihot, fit_vocabulary,
    load_annotations, topic_features,
)

DEFAULT_PLAN = ROOT / "experiments/municipal_v3/plan.json"
DEFAULT_BASE = ROOT / "reports/generated/municipal_v4_base"
DEFAULT_EXTRAS = ROOT / "data/processed/municipal_v3/object_features.csv"
DEFAULT_ANNOTATIONS = ROOT / "data/annotations/yes_effects_v4.json"
DEFAULT_OUTPUT = ROOT / "reports/generated/municipal_v4_semantics"
VARIANTS = (
    "v3_domain_multihot", "canonical_leaf", "canonical_hierarchy",
    "v3_domain_plus_effects", "canonical_leaf_plus_effects",
)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fold_features(train, evaluation, extras, base_numeric, base_categorical, variant):
    """Create design without target, fit all vocabularies on train objects only."""
    if variant not in VARIANTS:
        raise ValueError("Unknown structural variant")
    train_ids = set(train.vote_id.astype(str))
    train_objects = extras.loc[extras.vote_id.isin(train_ids)]
    vocabulary = {}
    if variant.startswith("v3_domain"):
        vocabulary["domains"] = fit_domain_vocabulary(train_objects)
        domain_features = encode_domains(extras, vocabulary["domains"])
        domain_features.index = extras.index
    else:
        field = "topic_nodes" if variant == "canonical_hierarchy" else "topic_leaves"
        vocabulary["topics"] = fit_vocabulary(train_objects, field)
        domain_features = encode_multihot(extras, field, vocabulary["topics"], "topic")
    features = extras[["vote_id"]].copy()
    features = pd.concat([features, domain_features], axis=1)
    numeric = list(base_numeric) + list(domain_features.columns)
    categorical = [
        col for col in base_categorical
        if not col.startswith(("object_domain_", "political_domain_"))
    ]
    if variant.endswith("plus_effects"):
        vocabulary["semantics"] = fit_vocabulary(train_objects, "semantic_tags")
        effects = encode_multihot(extras, "semantic_tags", vocabulary["semantics"], "effect")
        features = pd.concat([features, effects], axis=1)
        numeric.extend(effects.columns)
        # Explicit coverage indicator: unknown is not an evidenced false.
        features["semantic_documented"] = extras.semantic_documented.astype("uint8")
        numeric.append("semantic_documented")
    if len(set(numeric + categorical)) != len(numeric + categorical):
        raise ValueError("Duplicate estimator features")
    a = train.merge(features, on="vote_id", how="left", validate="many_to_one", sort=False)
    b = evaluation.merge(features, on="vote_id", how="left", validate="many_to_one", sort=False)
    if len(a) != len(train) or len(b) != len(evaluation):
        raise ValueError("Object feature join must preserve every municipality")
    if a[numeric].isna().any().any() or b[numeric].isna().any().any():
        # Original numeric variables are allowed missing; new multi-hot must not.
        new_cols = [c for c in numeric if c not in base_numeric]
        if a[new_cols].isna().any().any() or b[new_cols].isna().any().any():
            raise ValueError("New object features have missing encoded entries")
    coverage = {
        "train_annotated_objects": int(train_objects.semantic_documented.sum()),
        "train_total_objects": len(train_objects),
        "evaluation_annotated_objects": int(
            extras.loc[extras.vote_id.isin(set(evaluation.vote_id.astype(str))), "semantic_documented"].sum()
        ),
        "evaluation_total_objects": int(evaluation.vote_id.nunique()),
    }
    return a, b, numeric, categorical, vocabulary, coverage


def run(base, extras_path, annotations_path, plan_path, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Keep prior scores: use a new output directory")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan["training_start"] != "1990-01-01":
        raise ValueError("Expected identical V3 training start")
    if any(pd.Timestamp(w["end"]) >= pd.Timestamp("2023-01-01") for w in plan["validation_windows"]):
        raise ValueError("Never score previously exposed comparison dates")
    manifest = json.loads((base / "data_manifest.json").read_text(encoding="utf-8"))
    if _sha(base / "dataset.parquet") != manifest["dataset_sha256"]:
        raise ValueError("Base dataset fingerprint mismatch")
    base_numeric, base_categorical = baseline_features(manifest)
    columns = list(dict.fromkeys([
        "vote_id", "municipality_id", "vote_date", "yes_share",
        *base_numeric, *base_categorical,
    ]))
    data = pd.read_parquet(
        base / "dataset.parquet", columns=columns,
        filters=[("vote_date", "<", pd.Timestamp("2023-01-01")),
                 ("vote_date", ">=", pd.Timestamp("1990-01-01"))],
    )
    if data.vote_date.ge("2023-01-01").any():
        raise ValueError("Comparison targets must never be loaded")
    if data[["vote_id", "municipality_id"]].duplicated().any():
        raise ValueError("Duplicate municipality-object input keys")
    data["vote_id"] = data.vote_id.astype(str)
    raw = pd.read_csv(extras_path, dtype={"vote_id": "string"}, keep_default_na=True)
    for name in ("extra_domain_tokens_1", "extra_domain_tokens_2", "extra_domain_tokens_3"):
        raw[name] = raw[name].fillna("").astype(str)
    raw["vote_id"] = raw.vote_id.astype(str)
    topics = build_topic_table(raw)
    annotations = load_annotations(annotations_path)
    semantic = build_semantic_table(raw, annotations)
    extras = raw[["vote_id", "extra_domain_tokens_1",
                  "extra_domain_tokens_2", "extra_domain_tokens_3"]].merge(
        topics, on="vote_id", validate="one_to_one").merge(
        semantic, on="vote_id", validate="one_to_one")
    extras["topic_nodes"] = extras.topic_leaves.map(
        lambda value: topic_features(value, hierarchy=True))
    if extras.vote_id.duplicated().any() or not set(data.vote_id).issubset(set(extras.vote_id)):
        raise ValueError("Incomplete or duplicate semantic object coverage")
    output.mkdir(parents=True, exist_ok=True)
    record = {
        "status": "running", "scored_dates_end": "2022-12-31",
        "development_only": True, "strict_forecast_ready": False,
        "comparison_targets_loaded": False,
        "base_dataset_sha256": _sha(base / "dataset.parquet"),
        "v3_object_features_sha256": _sha(extras_path),
        "annotation_sha256": _sha(annotations_path),
        "implementation_sha256": _sha(Path(__file__)),
        "semantic_module_sha256": _sha(ROOT / "scripts/modeling/semantic_features_v4.py"),
        "plan_sha256": _sha(plan_path),
        "parameters": plan["regressor_parameters"],
        "annotation_votes_total": len(annotations["votes"]),
        "variants": [],
    }
    for variant in VARIANTS:
        predictions, folds = [], []
        for definition in plan["validation_windows"]:
            train = data[data.vote_date.lt(definition["start"])]
            evaluation = data[data.vote_date.between(definition["start"], definition["end"])]
            if train.empty or evaluation.empty or train.vote_date.max() >= evaluation.vote_date.min():
                raise ValueError("Invalid chronological window")
            a, b, numeric, categorical, vocabulary, coverage = fold_features(
                train, evaluation, extras, base_numeric, base_categorical, variant)
            estimator = ObjectProfileRegressor(
                numeric, categorical, **plan["regressor_parameters"])
            with threadpool_limits(limits=2):
                estimator.fit(a)
                predicted = estimator.predict(b.drop(columns=["yes_share"]))
            frame = b[["vote_id", "vote_date", "municipality_id", "yes_share"]].copy()
            frame["prediction"] = np.asarray(predicted, dtype=float)
            frame["window"] = definition["name"]
            if not np.isfinite(predicted).all():
                raise ValueError("Non-finite predictions")
            predictions.append(frame)
            score, _, _ = metrics(frame)
            folds.append({
                "window": definition["name"], "mae_pp": score["macro_object_mae_pp"],
                "coverage": coverage, "numeric_feature_count": len(numeric),
                "categorical_feature_count": len(categorical),
                "vocabulary": vocabulary,
            })
            print(f"{variant} / {definition['name']}: {score['macro_object_mae_pp']:.4f} pp",
                  flush=True)
            del estimator, a, b
            gc.collect()
        pred = pd.concat(predictions, ignore_index=True)
        overall, per_object, per_date = metrics(pred)
        per_object.to_csv(output / (variant + "_by_object.csv"), index=False)
        per_date.to_csv(output / (variant + "_by_date.csv"), index=False)
        record["variants"].append({
            "name": variant, "mae_pp": overall["macro_object_mae_pp"],
            "folds": folds, "scored_objects": int(pred.vote_id.nunique()),
            "scored_rows": len(pred),
        })
        print(f"FINAL {variant}: {overall['macro_object_mae_pp']:.4f} pp", flush=True)
        (output / "metrics.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    record["status"] = "complete"
    (output / "metrics.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--extras", type=Path, default=DEFAULT_EXTRAS)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    run(args.base, args.extras, args.annotations, args.plan, args.output)


if __name__ == "__main__":
    main()

"""Compare V4 semantics and V3 expanded polling on identical chronological objects.

This is a development-only *matched* experiment, not a new final test.
Both the V3 reference and all V4 variants are trained in the same run using
the frozen V3 object-profile parameters, the same V3 historical polls, and
the unchanged trend anchor. No 2023+ targets are loaded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from scripts.common.config import ROOT
from scripts.modeling.enrichment_experiment_v3 import baseline_features
from scripts.modeling.municipal_v2 import metrics, write_json
from scripts.modeling.object_profile_v2 import ObjectProfileRegressor
from scripts.modeling.poll_anchor import PollAnchoredRegressor, add_poll_features
from scripts.modeling.semantic_experiment_v4 import fold_features
from scripts.modeling.semantic_features_v4 import (
    build_semantic_table,
    build_topic_table,
    load_annotations,
    topic_features,
)

BASE = ROOT / "reports/generated/municipal_v4_base"
EXTRAS = ROOT / "data/processed/municipal_v3/object_features.csv"
ANNOTATIONS = ROOT / "data/annotations/yes_effects_v4.json"
CURRENT_POLLS = ROOT / "data/external/polls/srg_gfs_polls.csv"
HISTORICAL_POLLS = ROOT / "data/external/polls_historical_v3/polls.csv"
V3_PLAN = ROOT / "experiments/municipal_v3/plan.json"
PLAN = ROOT / "experiments/municipal_v4/poll_combination_plan.json"
OUTPUT = ROOT / "reports/generated/municipal_v4_poll_combination"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_protocol(plan, v3):
    """Require the exact fixed parameters and complete, chronological dates."""
    if plan["reference"] != "baseline_pca5":
        raise ValueError("Baseline must be the structural model behind the V3 7.62 MAE")
    if plan["variants"] != [
        "baseline_pca5", "v3_domain_multihot", "canonical_leaf",
        "canonical_hierarchy", "v3_domain_plus_effects",
        "canonical_leaf_plus_effects",
    ]:
        raise ValueError("Unknown or reordered variants")
    if plan["training_start"] != "1990-01-01":
        raise ValueError("Training period differs from V3")
    if plan["validation_windows"] != v3["validation_windows"]:
        raise ValueError("Chronological evaluation windows differ from V3")
    if plan["frozen_poll_parameters"] != v3["frozen_poll_parameters"]:
        raise ValueError("Poll correction differs from V3")
    if plan["regressor_parameters"] != v3["regressor_parameters"]:
        raise ValueError("Structural regressor parameters differ from V3")
    if plan["frozen_poll_parameters"]["trend_factor"] != 1.0:
        raise ValueError("The already chosen V3 trend factor must be retained")
    if any(pd.Timestamp(w["end"]) >= pd.Timestamp("2023-01-01") for w in plan["validation_windows"]):
        raise ValueError("Comparison-period targets cannot be scored")
    return True


def load_expanded_polls(base_path, historical_path):
    """Reuse the same two-source assembly and source-validation gates as V3."""
    a = pd.read_csv(base_path, dtype={"vote_key": "string"})
    b = pd.read_csv(historical_path, dtype={"vote_key": "string"})
    detailed = ["yes_certain", "yes_lean", "no_certain", "no_lean"]
    polls = pd.concat(
        [a.drop(columns=detailed), b.drop(columns=detailed, errors="ignore")],
        ignore_index=True,
    )
    if polls.duplicated(["vote_key", "wave"]).any():
        raise ValueError("The original and expanded poll collection overlap")
    return polls


def load_semantic_objects(extras_path, annotations_path):
    raw = pd.read_csv(extras_path, dtype={"vote_id": "string"}, keep_default_na=True)
    raw["vote_id"] = raw.vote_id.astype(str)
    for field in ("extra_domain_tokens_1", "extra_domain_tokens_2", "extra_domain_tokens_3"):
        raw[field] = raw[field].fillna("").astype(str)
    topic = build_topic_table(raw)
    semantic = build_semantic_table(raw, load_annotations(annotations_path))
    objects = raw[[
        "vote_id", "extra_domain_tokens_1", "extra_domain_tokens_2",
        "extra_domain_tokens_3",
    ]].merge(topic, on="vote_id", validate="one_to_one")
    objects = objects.merge(semantic, on="vote_id", validate="one_to_one")
    objects["topic_nodes"] = objects.topic_leaves.map(
        lambda value: topic_features(value, hierarchy=True)
    )
    if objects.vote_id.duplicated().any():
        raise ValueError("Repeated semantic object")
    return objects


def fit_one_fold(train, evaluation, extras, numeric, categorical, variant, params, poll_params):
    """Fit each model once; remove observed target from both prediction calls."""
    if train.vote_date.max() >= evaluation.vote_date.min():
        raise ValueError("All train dates must strictly precede this validation window")
    if variant == "baseline_pca5":
        a, b = train, evaluation
        features_n, features_c, vocabulary = list(numeric), list(categorical), {}
        coverage = {"train_annotated_objects": None, "evaluation_annotated_objects": None}
    else:
        a, b, features_n, features_c, vocabulary, coverage = fold_features(
            train, evaluation, extras, numeric, categorical, variant
        )
    if (b.groupby("vote_id").municipality_id.nunique() < 2).any():
        raise ValueError("National anchoring needs the entire municipal object")
    estimator = ObjectProfileRegressor(features_n, features_c, **params)
    with threadpool_limits(limits=2):
        estimator.fit(a)
        unlabelled = b.drop(columns=["yes_share"])
        structural = estimator.predict(unlabelled)
        anchor = PollAnchoredRegressor(estimator, **poll_params).fit(a)
        polled = anchor.predict(unlabelled)
    frame = b[[
        "municipality_id", "vote_id", "vote_date", "yes_share", "poll_available",
    ]].copy()
    frame["structural_prediction"] = structural
    frame["prediction"] = polled
    if frame[["structural_prediction", "prediction"]].isna().any().any():
        raise ValueError("Missing predictions")
    metadata = {
        "numeric_features": len(features_n),
        "categorical_features": len(features_c),
        "semantic_coverage": coverage,
        "vocabularies": vocabulary,
        "anchor_reference_date": anchor.audit_["reference_date"],
    }
    return frame, metadata


def summarize(predictions):
    metric, objects, dates = metrics(predictions)
    availability = predictions.groupby("vote_id").poll_available.nunique(dropna=False)
    if availability.gt(1).any():
        raise ValueError("Poll coverage differs between municipalities of the same object")
    by_id = predictions[["vote_id", "poll_available"]].drop_duplicates("vote_id")
    objects = objects.merge(by_id, on="vote_id", validate="one_to_one")
    category = {}
    for label, selected in [
        ("polled", objects.poll_available.eq(1.0)),
        ("unpolled", objects.poll_available.eq(0.0)),
    ]:
        portion = objects.loc[selected]
        category[label] = {
            "objects": len(portion),
            "macro_mae_pp": float(portion.mae_pp.mean()) if len(portion) else None,
        }
    return metric, objects, dates, category


def paired_date_bootstrap(object_scores, reference, other, repeats=3000):
    """Descriptive resampling of COMPLETE dates, never municipality rows."""
    table = object_scores.pivot(index="vote_id", columns="variant", values="mae_pp")
    metadata = object_scores[["vote_id", "vote_date"]].drop_duplicates("vote_id")
    table = metadata.merge(table, on="vote_id", validate="one_to_one")
    if table[[reference, other]].isna().any().any():
        raise ValueError("Every object must have paired model metrics")
    delta = table[reference].to_numpy() - table[other].to_numpy()
    labels, groups = np.unique(table.vote_date.to_numpy(), return_inverse=True)
    if len(labels) != 23:
        raise ValueError("Expected 23 complete development voting dates")
    rng = np.random.default_rng(20261123)
    estimates = []
    for _ in range(repeats):
        draws = rng.integers(0, len(labels), size=len(labels))
        multiplicity = np.bincount(draws, minlength=len(labels))[groups]
        estimates.append(float(np.average(delta, weights=multiplicity)))
    return [float(q) for q in np.quantile(estimates, [0.025, 0.975])]


def run(base, extras_path, annotations_path, polls_base, polls_historical, plan_path, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Do not overwrite a score; choose a new output location")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    original = json.loads(V3_PLAN.read_text(encoding="utf-8"))
    check_protocol(plan, original)
    manifest = json.loads((base / "data_manifest.json").read_text(encoding="utf-8"))
    if manifest["dataset_sha256"] != sha(base / "dataset.parquet"):
        raise ValueError("Prepared data hash mismatch")
    numeric, categorical = baseline_features(manifest)
    selected = list(dict.fromkeys([
        "municipality_id", "vote_id", "vote_key", "vote_date", "yes_share",
        "statpop_pop_total", "statpop_share_foreign", "statpop_share_0_19",
        *numeric, *categorical,
    ]))
    data = pd.read_parquet(
        base / "dataset.parquet", columns=selected,
        filters=[("vote_date", ">=", pd.Timestamp(plan["training_start"])),
                 ("vote_date", "<", pd.Timestamp("2023-01-01"))],
    )
    if data.vote_date.ge("2023-01-01").any():
        raise ValueError("Future outcomes read during evaluation")
    data["vote_id"] = data.vote_id.astype(str)
    if data[["municipality_id", "vote_id"]].duplicated().any():
        raise ValueError("Duplicate municipality-object keys")
    polls = load_expanded_polls(polls_base, polls_historical)
    data, poll_audit = add_poll_features(data, polls)
    objects = load_semantic_objects(extras_path, annotations_path)
    if not set(data.vote_id).issubset(set(objects.vote_id)):
        raise ValueError("Missing semantic object identities")
    output.mkdir(parents=True, exist_ok=True)
    all_records = []
    scores = []
    paths = [base / "dataset.parquet", base / "data_manifest.json",
             extras_path, annotations_path, polls_base, polls_historical,
             V3_PLAN, plan_path, Path(__file__)]
    manifest_out = {
        "status": "running", "protocol": plan,
        "evidence_sha256": {str(p.relative_to(ROOT)): sha(p) for p in paths},
        "same_population_for_all_variants": True,
        "comparison_targets_loaded": False,
        "forecast_ready": False,
        "poll_source_audit": {
            "poll_rows": len(polls),
            "poll_objects_in_data": poll_audit["poll_objects"],
            "objects_with_prior_admissible_poll": poll_audit["objects_with_prior_admissible_poll"],
        },
        "runs": [],
    }
    write_json(output / "manifest.json", manifest_out)
    for variant in plan["variants"]:
        blocks = []
        fold_scores = []
        for window in plan["validation_windows"]:
            train = data.loc[data.vote_date.lt(window["start"])]
            evaluation = data.loc[data.vote_date.between(window["start"], window["end"])]
            frame, metadata = fit_one_fold(
                train, evaluation, objects, numeric, categorical,
                variant, plan["regressor_parameters"], plan["frozen_poll_parameters"],
            )
            frame["window"] = window["name"]
            blocks.append(frame)
            score, _, _, subset = summarize(
                frame.rename(columns={"prediction": "prediction"})
            )
            fold_scores.append({
                "window": window["name"],
                "mae_pp": score["macro_object_mae_pp"],
                "objects": score["objects"],
                "poll_subsets": subset,
                **metadata,
            })
            print(f"{variant} {window['name']} MAE {score['macro_object_mae_pp']:.4f} pp", flush=True)
        frame = pd.concat(blocks, ignore_index=True)
        if len(frame) != 138868 or frame.vote_id.nunique() != 66:
            raise ValueError("The experiment must retain the exact 66/138868 object population")
        score, per_obj, per_date, subsets = summarize(frame)
        structural_frame = frame.drop(columns=["prediction"]).rename(
            columns={"structural_prediction": "prediction"}
        )
        structural_score, _, _ = metrics(structural_frame)
        per_obj["variant"] = variant
        scores.append(per_obj)
        frame.to_parquet(output / f"{variant}_predictions.parquet", index=False)
        per_obj.to_csv(output / f"{variant}_by_object.csv", index=False)
        per_date.to_csv(output / f"{variant}_by_date.csv", index=False)
        row = {
            "variant": variant,
            "macro_object_mae_pp": score["macro_object_mae_pp"],
            "structural_mae_pp": structural_score["macro_object_mae_pp"],
            "poll_subsets": subsets,
            "folds": fold_scores,
            "prediction_sha256": sha(output / f"{variant}_predictions.parquet"),
        }
        all_records.append(row)
        manifest_out["runs"].append(row)
        write_json(output / "manifest.json", manifest_out)
        print(f"RESULT {variant} structural={row['structural_mae_pp']:.4f}"
              f" +V3 polls={row['macro_object_mae_pp']:.4f}", flush=True)
    by_object = pd.concat(scores, ignore_index=True)
    by_object.to_csv(output / "paired_by_object.csv", index=False)
    reference = all_records[0]
    if abs(reference["macro_object_mae_pp"] - plan["reference_expected_mae_pp"]) > 0.0002:
        raise ValueError("Cannot compare: V3 7.6183-point reference was not reproduced")
    if abs(reference["structural_mae_pp"] - plan["reference_expected_structural_mae_pp"]) > 0.0002:
        raise ValueError("Cannot compare: V3 structural baseline did not reproduce")
    ref_keys = pd.read_parquet(output / "baseline_pca5_predictions.parquet")[
        ["vote_id", "municipality_id", "vote_date", "yes_share", "poll_available"]
    ]
    for variant in plan["variants"][1:]:
        keys = pd.read_parquet(output / f"{variant}_predictions.parquet")[
            ["vote_id", "municipality_id", "vote_date", "yes_share", "poll_available"]
        ]
        pd.testing.assert_frame_equal(keys.reset_index(drop=True), ref_keys.reset_index(drop=True))
    comparisons = []
    for row in all_records[1:]:
        interval = paired_date_bootstrap(by_object, "baseline_pca5", row["variant"])
        comparisons.append({
            "variant": row["variant"],
            "improvement_pp_positive_is_better":
                reference["macro_object_mae_pp"] - row["macro_object_mae_pp"],
            "date_bootstrap_95pct_descriptive": interval,
        })
    manifest_out["status"] = "complete"
    manifest_out["reference_reproduced"] = True
    manifest_out["reference_mae_pp"] = reference["macro_object_mae_pp"]
    manifest_out["comparisons"] = comparisons
    write_json(output / "manifest.json", manifest_out)
    return manifest_out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--extras", type=Path, default=EXTRAS)
    parser.add_argument("--annotations", type=Path, default=ANNOTATIONS)
    parser.add_argument("--polls-original", type=Path, default=CURRENT_POLLS)
    parser.add_argument("--polls-historical", type=Path, default=HISTORICAL_POLLS)
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    run(args.base, args.extras, args.annotations, args.polls_original,
        args.polls_historical, args.plan, args.output)


if __name__ == "__main__":
    main()

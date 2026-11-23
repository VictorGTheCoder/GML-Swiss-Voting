"""Audit V5 historical YES-effect enrichment against the fixed V3 7.6183 MAE.

No outcome after 2022 is loaded. Every model retains the same historical
frozen polling collection, national population anchor, PCA5+XGBoost settings,
the same municipalities and voting dates and all votes without polling.
"""

from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path

import pandas as pd
from threadpoolctl import threadpool_limits

from scripts.common.config import ROOT
from scripts.modeling.enrichment_experiment_v3 import baseline_features
from scripts.modeling.municipal_v2 import metrics, write_json
from scripts.modeling.object_enrichment_v3 import encode_domains, fit_domain_vocabulary
from scripts.modeling.object_profile_v2 import ObjectProfileRegressor
from scripts.modeling.poll_anchor import PollAnchoredRegressor, add_poll_features
from scripts.modeling.semantic_features_v4 import load_annotations
from scripts.modeling.semantic_labels_v5 import (
    HISTORICAL,
    V4,
    build_coarse_table,
    encode_tags,
    load_history,
    vocabulary,
)
from scripts.modeling.semantic_poll_comparison_v4 import (
    CURRENT_POLLS,
    EXTRAS,
    HISTORICAL_POLLS,
    V3_PLAN,
    load_expanded_polls,
    paired_date_bootstrap,
    sha,
    summarize,
)

BASE = ROOT / "reports/generated/municipal_v5_base"
OUTPUT = ROOT / "reports/generated/municipal_v5_historical_semantics"
PLAN = ROOT / "experiments/municipal_v5/plan.json"

VARIANTS = (
    "baseline_pca5",
    "v3_domain_multihot",
    "baseline_coarse_mechanisms",
    "baseline_coarse_all",
    "v3_domains_coarse_mechanisms",
    "v3_domains_coarse_all",
)


def check_plan(plan, original):
    """Fail if a known V3 parameter, horizon or validation unit is changed."""
    for key in ("training_start", "validation_windows", "regressor_parameters", "frozen_poll_parameters"):
        if plan[key] != original[key]:
            raise ValueError(f"V5 changes frozen V3 parameter or window: {key}")
    if tuple(plan["variants"]) != VARIANTS or plan["reference"] != "baseline_pca5":
        raise ValueError("Unknown or reordered model candidates")
    if plan["mechanism_min_support_in_training_objects"] != 3:
        raise ValueError("V5 frequency support must remain fixed")
    if any(pd.Timestamp(w["end"]) >= pd.Timestamp("2023-01-01") for w in plan["validation_windows"]):
        raise ValueError("Evaluation after 2022 is forbidden")
    if plan["frozen_poll_parameters"]["trend_factor"] != 1.0:
        raise ValueError("The V3 two-wave trend must remain unchanged")
    return True


def fold_features(train, evaluation, extras, numeric, categorical, variant, min_support):
    """Fit domain vocabulary and broad semantic vocabulary on TRAIN vote ids."""
    if variant not in VARIANTS:
        raise ValueError("Unrecognized experiment")
    if variant == "baseline_pca5":
        return train, evaluation, list(numeric), list(categorical), {}, {
            "train_annotated": 0, "test_annotated": 0, "mechanism_tokens": 0,
        }
    train_ids = set(train.vote_id.astype(str).unique())
    test_ids = set(evaluation.vote_id.astype(str).unique())
    train_objects = extras[extras.vote_id.isin(train_ids)]
    eval_objects = extras[extras.vote_id.isin(test_ids)]
    selected = extras[["vote_id"]].copy()
    new_numeric = list(numeric)
    new_categorical = list(categorical)
    vocabularies = {}
    if variant == "v3_domain_multihot" or variant.startswith("v3_domains_"):
        vocabularies["swissvotes"] = fit_domain_vocabulary(train_objects)
        domains = encode_domains(extras, vocabularies["swissvotes"])
        selected = pd.concat([selected, domains], axis=1)
        new_numeric += list(domains.columns)
        new_categorical = [
            c for c in new_categorical
            if not c.startswith(("object_domain_", "political_domain_"))
        ]
    if "coarse_" in variant:
        complete_vocab = vocabulary(train_objects, min_count=min_support)
        tags = complete_vocab if variant.endswith("_all") else [
            tag for tag in complete_vocab if tag.startswith("mechanism_")
        ]
        vocabularies["coarse"] = tags
        if tags:
            encoded = encode_tags(extras, tags)
            selected = pd.concat([selected, encoded], axis=1)
            new_numeric += list(encoded.columns)
            # Explicit unknown/known indicator, only if both appear in training
            # and actual known tags exist; avoid constant XGB column-RNG changes.
            if train_objects.coarse_documented.nunique() > 1:
                selected["coarse_documented"] = extras.coarse_documented.astype("uint8")
                new_numeric.append("coarse_documented")
    if len(set(new_numeric + new_categorical)) != len(new_numeric + new_categorical):
        raise ValueError("Duplicate feature names in estimator")
    a = train.merge(selected, on="vote_id", validate="many_to_one", how="left", sort=False)
    b = evaluation.merge(selected, on="vote_id", validate="many_to_one", how="left", sort=False)
    if len(a) != len(train) or len(b) != len(evaluation):
        raise ValueError("All municipality rows must be preserved")
    appended = [c for c in new_numeric if c not in numeric]
    if a[appended].isna().any().any() or b[appended].isna().any().any():
        raise ValueError("Missing newly encoded features")
    coverage = {
        "train_annotated": int(train_objects.coarse_documented.sum()),
        "train_objects": len(train_objects),
        "test_annotated": int(eval_objects.coarse_documented.sum()),
        "test_objects": len(eval_objects),
        "mechanism_tokens": len(vocabularies.get("coarse", [])),
    }
    return a, b, new_numeric, new_categorical, vocabularies, coverage


def prepare_data(base, extras_path, historical_path, current_path, poll1, poll2, plan):
    manifest = json.loads((base / "data_manifest.json").read_text(encoding="utf-8"))
    if manifest["dataset_sha256"] != sha(base / "dataset.parquet"):
        raise ValueError("Original prepared dataset hash mismatch")
    numeric, categorical = baseline_features(manifest)
    columns = list(dict.fromkeys([
        "vote_id", "municipality_id", "vote_key", "vote_date", "yes_share",
        "statpop_pop_total", "statpop_share_foreign", "statpop_share_0_19",
        *numeric, *categorical,
    ]))
    data = pd.read_parquet(
        base / "dataset.parquet", columns=columns,
        filters=[("vote_date", ">=", pd.Timestamp(plan["training_start"])),
                 ("vote_date", "<", pd.Timestamp("2023-01-01"))],
    )
    if data.vote_date.ge("2023-01-01").any():
        raise ValueError("Comparison-period target data leaked")
    data["vote_id"] = data.vote_id.astype(str)
    if data[["vote_id", "municipality_id"]].duplicated().any():
        raise ValueError("Duplicate municipal targets")
    polls = load_expanded_polls(poll1, poll2)
    data, poll_audit = add_poll_features(data, polls)
    objects = pd.read_csv(
        extras_path, dtype={"vote_id": str, "vote_key": str},
        usecols=["vote_id", "vote_date"],
    )
    objects["vote_id"] = objects.vote_id.astype(str)
    semantic = build_coarse_table(
        objects, load_history(historical_path), load_annotations(current_path)
    )
    extras = objects[["vote_id"]].merge(
        semantic, on="vote_id", validate="one_to_one",
    )
    if not set(data.vote_id).issubset(set(extras.vote_id)):
        raise ValueError("Source annotations do not match all modeled vote IDs")
    v3_extra = pd.read_csv(
        extras_path, dtype={"vote_id": str},
        usecols=["vote_id", "extra_domain_tokens_1",
                 "extra_domain_tokens_2", "extra_domain_tokens_3"],
        keep_default_na=False,
    )
    v3_extra["vote_id"] = v3_extra.vote_id.astype(str)
    extras = extras.merge(v3_extra, on="vote_id", validate="one_to_one", sort=False)
    return data, extras, numeric, categorical, poll_audit


def run(base=BASE, extras_path=EXTRAS, historical_path=HISTORICAL,
        current_path=V4, poll1=CURRENT_POLLS, poll2=HISTORICAL_POLLS,
        plan_path=PLAN, output=OUTPUT):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Cannot overwrite an existing experimental run")
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    check_plan(plan, json.loads(V3_PLAN.read_text(encoding="utf-8")))
    data, extras, numeric, categorical, poll_audit = prepare_data(
        base, extras_path, historical_path, current_path, poll1, poll2, plan
    )
    output.mkdir(parents=True, exist_ok=True)
    evidence_paths = [base / "dataset.parquet", base / "data_manifest.json",
                      extras_path, historical_path, current_path, poll1, poll2,
                      plan_path, V3_PLAN, Path(__file__).resolve(),
                      ROOT / "scripts/modeling/semantic_labels_v5.py"]
    record = {
        "status": "running", "protocol": plan,
        "input_sha256": {
            str(p.resolve().relative_to(ROOT)): sha(p) for p in evidence_paths
        },
        "poll_audit": {
            "source_rows": len(pd.read_csv(poll1)) + len(pd.read_csv(poll2)),
            "objects_with_polls_in_dataset": poll_audit["poll_objects"],
            "objects_with_two_waves": poll_audit["objects_with_prior_admissible_poll"],
        },
        "strict_forecast_ready": False,
        "comparison_targets_loaded": False,
        "same_population_all_variants": True,
        "runs": [],
    }
    write_json(output / "manifest.json", record)
    object_scores = []
    expected_keys = None
    for variant in VARIANTS:
        predictions, folds = [], []
        for window in plan["validation_windows"]:
            train = data[data.vote_date.lt(window["start"])]
            evaluation = data[data.vote_date.between(window["start"], window["end"])]
            if train.empty or evaluation.empty or train.vote_date.max() >= evaluation.vote_date.min():
                raise ValueError("Fold chronological separation failed")
            a, b, use_n, use_c, vocab, coverage = fold_features(
                train, evaluation, extras, numeric, categorical, variant,
                plan["mechanism_min_support_in_training_objects"],
            )
            model = ObjectProfileRegressor(use_n, use_c, **plan["regressor_parameters"])
            with threadpool_limits(limits=2):
                model.fit(a)
                predict_frame = b.drop(columns=["yes_share"])
                structural = model.predict(predict_frame)
                anchor = PollAnchoredRegressor(
                    model, **plan["frozen_poll_parameters"]
                ).fit(a)
                adjusted = anchor.predict(predict_frame)
            frame = b[[
                "municipality_id", "vote_id", "vote_date", "yes_share", "poll_available"
            ]].copy()
            frame["structural_prediction"] = structural
            frame["prediction"] = adjusted
            frame["window"] = window["name"]
            predictions.append(frame)
            fold_metric, _, _, subsets = summarize(frame)
            folds.append({
                "window": window["name"],
                "mae_pp": fold_metric["macro_object_mae_pp"],
                "polled_unpolled": subsets,
                "annotated": coverage,
                "numeric_feature_count": len(use_n),
                "categorical_feature_count": len(use_c),
                "vocabularies": vocab,
            })
            print(f"{variant} {window['name']}: {fold_metric['macro_object_mae_pp']:.4f} pp"
                  f" (annotated train={coverage['train_annotated']})", flush=True)
            del model, anchor, a, b
            gc.collect()
        total = pd.concat(predictions, ignore_index=True)
        if total.vote_id.nunique() != 66 or len(total) != 138868 or total.vote_date.nunique() != 23:
            raise ValueError("Wrong evaluation population")
        keys = total[["municipality_id", "vote_id", "vote_date", "yes_share", "poll_available"]]
        if expected_keys is None:
            expected_keys = keys.reset_index(drop=True)
        else:
            pd.testing.assert_frame_equal(expected_keys, keys.reset_index(drop=True))
        score, per_obj, per_date, subsets = summarize(total)
        structural = total.drop(columns=["prediction"]).rename(
            columns={"structural_prediction": "prediction"}
        )
        structural_score, _, _ = metrics(structural)
        per_obj["variant"] = variant
        object_scores.append(per_obj)
        per_obj.to_csv(output / f"{variant}_by_object.csv", index=False)
        per_date.to_csv(output / f"{variant}_by_date.csv", index=False)
        # Preserve all municipal outputs so a model can be reproduced and inspected.
        total.to_parquet(output / f"{variant}_predictions.parquet", index=False)
        item = {
            "variant": variant,
            "macro_object_mae_pp": score["macro_object_mae_pp"],
            "structural_mae_pp": structural_score["macro_object_mae_pp"],
            "polled_unpolled": subsets,
            "folds": folds,
            "predictions_sha256": sha(output / f"{variant}_predictions.parquet"),
        }
        record["runs"].append(item)
        write_json(output / "manifest.json", record)
        print(f"RESULT {variant}: {item['macro_object_mae_pp']:.4f}"
              f" (structural {item['structural_mae_pp']:.4f})", flush=True)
    first = record["runs"][0]
    if abs(first["macro_object_mae_pp"] - plan["reference_expected_mae_pp"]) > 0.0002:
        raise ValueError("V3 expanded poll baseline was not reproduced")
    if abs(first["structural_mae_pp"] - plan["reference_expected_structural_mae_pp"]) > 0.0002:
        raise ValueError("V3 structural baseline was not reproduced")
    combined = pd.concat(object_scores, ignore_index=True)
    combined.to_csv(output / "paired_by_object.csv", index=False)
    comparisons = []
    for item in record["runs"][1:]:
        comparisons.append({
            "variant": item["variant"],
            "gain_pp_positive_is_better": first["macro_object_mae_pp"] - item["macro_object_mae_pp"],
            "paired_bootstrap_95pct_dates": paired_date_bootstrap(
                combined, "baseline_pca5", item["variant"]
            ),
        })
    record.update({
        "status": "complete",
        "reference_reproduced": True,
        "reference_mae_pp": first["macro_object_mae_pp"],
        "comparisons": comparisons,
    })
    write_json(output / "manifest.json", record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--extras", type=Path, default=EXTRAS)
    parser.add_argument("--historical", type=Path, default=HISTORICAL)
    parser.add_argument("--current", type=Path, default=V4)
    parser.add_argument("--polls-original", type=Path, default=CURRENT_POLLS)
    parser.add_argument("--polls-historical", type=Path, default=HISTORICAL_POLLS)
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    run(args.base, args.extras, args.historical, args.current,
        args.polls_original, args.polls_historical, args.plan, args.output)


if __name__ == "__main__":
    main()

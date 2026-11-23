"""Small declared ablation campaign for new object data and communal prototypes.

Only the established development dates 2016--2022 are scored. Training starts
in 1990 as in the frozen V2 candidate. No selection or forecast files from V2
are changed. Every structural fit is reused for its fixed polling comparisons.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from scripts.common.config import ROOT
from scripts.modeling.municipal_v2 import code_hashes, environment, metrics, write_json
from scripts.modeling.object_enrichment_v3 import encode_domains, fit_domain_vocabulary
from scripts.modeling.object_profile_v2 import ObjectProfileRegressor
from scripts.modeling.poll_anchor import PollAnchoredRegressor, add_poll_features
from scripts.modeling.prototype_profile_v3 import PrototypeProfileRegressor

PLAN_PATH = ROOT / "experiments/municipal_v3/plan.json"
DEFAULT_OUTPUT = ROOT / "reports/generated/municipal_v3_experiments"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def baseline_features(manifest):
    return (list(manifest["political"]["object_numeric_features"]),
            ["object_legal_form", "object_domain_1", "object_domain_2", "object_domain_3"]
            + list(manifest["political"]["object_categorical_features"]))


def assemble_fold(train, evaluation, manifest, extras, extra_manifest, configuration):
    """Choose the fixed feature block, learning only its domain vocabulary."""
    numeric, categorical = baseline_features(manifest)
    selected = []
    for group in configuration["groups"]:
        numeric += extra_manifest["groups"][group]["numeric"]
        categorical += extra_manifest["groups"][group]["categorical"]
        selected += extra_manifest["groups"][group]["numeric"] + extra_manifest["groups"][group]["categorical"]
    table = extras[["vote_id", *selected]].copy()
    vocabulary = None
    if configuration.get("domain_multihot"):
        vocabulary = fit_domain_vocabulary(extras[extras.vote_id.isin(train.vote_id.unique())])
        encoded = encode_domains(extras, vocabulary)
        table = pd.concat([table, encoded], axis=1)
        numeric += list(encoded)
        categorical = [c for c in categorical if not c.startswith(("object_domain_", "political_domain_"))]
    # Checked one-to-one before preparing the campaign. Each join preserves rows.
    a = train.merge(table, on="vote_id", how="left", sort=False, validate="many_to_one")
    b = evaluation.merge(table, on="vote_id", how="left", sort=False, validate="many_to_one")
    return a, b, numeric, categorical, vocabulary


def diagnostics(predictions):
    rows = []
    for vote_id, group in predictions.groupby("vote_id", sort=False):
        residual = group.yes_share.to_numpy(float) - group.prediction.to_numpy(float)
        offset = float(np.median(residual))
        rows.append({"vote_id": vote_id, "vote_date": group.vote_date.iloc[0],
                     "mae_pp": float(np.abs(residual).mean() * 100),
                     "mean_bias_pp": float(-residual.mean() * 100),
                     "oracle_median_offset_pp": offset * 100,
                     "oracle_offset_mae_pp": float(np.abs(residual - offset).mean() * 100)})
    return pd.DataFrame(rows)


def _model(configuration, numeric, categorical, parameters):
    if configuration["basis"] == "pca":
        return ObjectProfileRegressor(numeric, categorical, **parameters)
    return PrototypeProfileRegressor(numeric, categorical, **parameters,
                                    n_prototypes=6, temperature="auto")


def _code_evidence():
    evidence = code_hashes()
    paths = [Path(__file__), ROOT / "scripts/modeling/object_enrichment_v3.py",
             ROOT / "scripts/modeling/prototype_profile_v3.py"]
    evidence.update({str(p.relative_to(ROOT)): sha(p) for p in paths})
    return evidence


def run(input_dir, extra_dir, output, plan_path):
    plan = json.loads(plan_path.read_text())
    if plan["training_start"] != "1990-01-01":
        raise ValueError("This fixed comparison requires the V2 training start 1990-01-01")
    if any(pd.Timestamp(w["end"]) >= pd.Timestamp("2023-01-01") for w in plan["validation_windows"]):
        raise ValueError("V3 development windows must end before 2023")
    output.mkdir(parents=True, exist_ok=True)
    if (output / "campaign.json").exists():
        raise FileExistsError("Preserve completed or interrupted campaign; use a new output directory")
    manifest = json.loads((input_dir / "data_manifest.json").read_text())
    extra_manifest = json.loads((extra_dir / "manifest.json").read_text())
    if sha(input_dir / "dataset.parquet") != manifest["dataset_sha256"]:
        raise ValueError("Base dataset hash mismatch")
    if sha(extra_dir / "object_features.csv") != extra_manifest["features_sha256"]:
        raise ValueError("Extra object feature hash mismatch")
    if manifest.get("preparation_code") != code_hashes() or manifest.get("preparation_environment") != environment():
        raise ValueError("Base preparation provenance or runtime changed")
    original_polls_sha256 = sha(ROOT / "data/external/polls/srg_gfs_polls.csv")
    if original_polls_sha256 != manifest["polls"]["sha256"]:
        raise ValueError("Original poll source changed since base preparation")
    base_numeric, base_categorical = baseline_features(manifest)
    poll_columns = ["poll_yes_share", "poll_no_share", "poll_undecided_share", "poll_available",
                    "poll_population_weight", "poll_yes_trend_per_day", "poll_days_to_vote",
                    "poll_trend_available"]
    selected_columns = ["municipality_id", "vote_id", "vote_key", "vote_date", "canton", "yes_share",
                        *base_numeric, *base_categorical, *poll_columns]
    data = pd.read_parquet(input_dir / "dataset.parquet", columns=selected_columns,
                           filters=[("vote_date", "<", pd.Timestamp("2023-01-01")),
                                    ("vote_date", ">=", pd.Timestamp("1990-01-01"))])
    if data.vote_date.ge("2023-01-01").any():
        raise ValueError("The V3 experiment must not read comparison-period targets")
    extras = pd.read_csv(extra_dir / "object_features.csv", dtype={"vote_id": "string", "vote_key": "string"},
                         keep_default_na=True)
    for field in extra_manifest["domain_token_fields"]:
        extras[field] = extras[field].fillna("").astype(str)
    # CSV string dtype is required for categorical source codes, including dep.
    for column in extra_manifest["categorical_features"]:
        extras[column] = extras[column].astype("string").str.replace(r"\.0$", "", regex=True)
    if extras.vote_id.duplicated().any() or not data.vote_id.astype(str).isin(extras.vote_id).all():
        raise ValueError("Extra object features do not exactly cover the modeled objects")
    reference = data[["vote_id", "vote_key", "vote_date"]].drop_duplicates("vote_id").set_index("vote_id")
    matched = extras.set_index("vote_id").reindex(reference.index)
    if not np.array_equal(reference.vote_key.astype(str).to_numpy(), matched.vote_key.astype(str).to_numpy()):
        raise ValueError("Extra object vote keys disagree with the base dataset")
    if not np.array_equal(reference.vote_date.to_numpy(), pd.to_datetime(matched.vote_date).to_numpy()):
        raise ValueError("Extra object dates disagree with the base dataset")
    evidence = {"started_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": "running", "plan": plan, "plan_sha256": sha(plan_path),
                "code": _code_evidence(), "environment": environment(),
                "dataset_sha256": sha(input_dir / "dataset.parquet"),
                "base_manifest_sha256": sha(input_dir / "data_manifest.json"),
                "original_polls_sha256": original_polls_sha256,
                "extra_features_sha256": sha(extra_dir / "object_features.csv"),
                "evaluation_end": "2022-12-31", "comparison_targets_loaded": False,
                "strict_forecast_ready": False, "runs": []}
    write_json(output / "campaign.json", evidence)
    started = time.monotonic()
    for config in plan["structural_variants"]:
        fold_records, predictions, polled_predictions = [], [], []
        t0 = time.monotonic()
        for definition in plan["validation_windows"]:
            train = data[data.vote_date.lt(definition["start"])].copy()
            evaluation = data[data.vote_date.between(definition["start"], definition["end"])].copy()
            if train.vote_date.max() >= evaluation.vote_date.min():
                raise ValueError("Training/evaluation date overlap")
            a, b, numeric, categorical, vocabulary = assemble_fold(
                train, evaluation, manifest, extras, extra_manifest, config)
            # No current outcome-derived column is in the explicit feature lists.
            model = _model(config, numeric, categorical, plan["regressor_parameters"])
            with threadpool_limits(limits=2):
                model.fit(a)
                # Remove outcomes to exercise the actual prediction contract.
                predict_frame = b.drop(columns=["yes_share"])
                prediction = model.predict(predict_frame)
                anchored = PollAnchoredRegressor(model, **plan["frozen_poll_parameters"]).fit(a)
                polled = anchored.predict(predict_frame)
            p = b[["municipality_id", "vote_id", "vote_date", "canton", "yes_share"]].copy()
            p["prediction"] = prediction
            p["window"] = definition["name"]
            q = p.assign(prediction=polled)
            predictions.append(p)
            polled_predictions.append(q)
            score, _, _ = metrics(p)
            fold_records.append({"window": definition["name"], "metrics": score,
                                 "model_audit": model.audit_, "domain_vocabulary": vocabulary,
                                 "numeric_features": numeric, "categorical_features": categorical})
            write_json(output / (config["name"] + "_progress.json"),
                       {"configuration": config, "completed_folds": fold_records})
            print(f"{config['name']} {definition['name']}: {score['macro_object_mae_pp']:.4f} pp", flush=True)
            del model, anchored, a, b, train, evaluation
            gc.collect()
        prediction_table = pd.concat(predictions, ignore_index=True)
        poll_table = pd.concat(polled_predictions, ignore_index=True)
        score, objects, dates = metrics(prediction_table)
        poll_score, _, _ = metrics(poll_table)
        prefix = output / config["name"]
        prediction_table.to_parquet(str(prefix) + "_predictions.parquet", index=False)
        poll_table.to_parquet(str(prefix) + "_current_polls_predictions.parquet", index=False)
        objects.to_csv(str(prefix) + "_by_object.csv", index=False)
        dates.to_csv(str(prefix) + "_by_date.csv", index=False)
        diagnostic = diagnostics(prediction_table)
        diagnostic.to_csv(str(prefix) + "_diagnostics.csv", index=False)
        record = {"name": config["name"], "configuration": config, "status": "complete",
                  "metrics": score, "current_poll_metrics": poll_score,
                  "elapsed_seconds": time.monotonic() - t0, "folds": fold_records,
                  "oracle_offset_mae_pp": float(diagnostic.oracle_offset_mae_pp.mean()),
                  "mean_absolute_object_bias_pp": float(diagnostic.mean_bias_pp.abs().mean()),
                  "oracle_is_forecast": False,
                  "predictions_sha256": sha(str(prefix) + "_predictions.parquet")}
        evidence["runs"].append(record)
        write_json(output / "campaign.json", evidence)
        print(f"COMPLETE {config['name']}: {score['macro_object_mae_pp']:.4f}; current polls {poll_score['macro_object_mae_pp']:.4f}", flush=True)
    evidence["status"] = "complete"
    evidence["elapsed_seconds"] = time.monotonic() - started
    write_json(output / "campaign.json", evidence)


class CachedPredictionModel:
    """Reuse fixed structural predictions when testing a new poll collection."""
    def __init__(self, predictions):
        self.values = predictions.set_index(["municipality_id", "vote_id"]).prediction

    def predict(self, frame):
        index = pd.MultiIndex.from_frame(frame[["municipality_id", "vote_id"]])
        values = self.values.reindex(index)
        if values.isna().any():
            raise ValueError("Missing cached structural prediction")
        return values.to_numpy(float)


def polling_comparison(input_dir, campaign_dir, historical_polls, output):
    """Evaluate new coverage with the previously frozen structural predictions."""
    output.mkdir(parents=True, exist_ok=True)
    if (output / "polling_comparison.json").exists():
        raise FileExistsError("Preserve existing polling comparison")
    campaign = json.loads((campaign_dir / "campaign.json").read_text())
    if campaign["status"] != "complete":
        raise ValueError("Complete the structural campaign first")
    if sha(input_dir / "dataset.parquet") != campaign["dataset_sha256"]:
        raise ValueError("Base dataset changed since the structural campaign")
    if campaign["code"] != _code_evidence():
        raise ValueError("Model implementation changed since the structural campaign")
    if sha(input_dir / "data_manifest.json") != campaign["base_manifest_sha256"]:
        raise ValueError("Base manifest changed since the structural campaign")
    if sha(ROOT / "data/external/polls/srg_gfs_polls.csv") != campaign["original_polls_sha256"]:
        raise ValueError("Original poll collection changed since the structural campaign")
    base = pd.read_csv(ROOT / "data/external/polls/srg_gfs_polls.csv", dtype={"vote_key": "string"})
    historical = pd.read_csv(historical_polls, dtype={"vote_key": "string"})
    detailed = ["yes_certain", "yes_lean", "no_certain", "no_lean"]
    combined = pd.concat([base.drop(columns=detailed), historical.drop(columns=detailed, errors="ignore")], ignore_index=True)
    if combined.duplicated(["vote_key", "wave"]).any():
        raise ValueError("Historical polls overlap the frozen collection")
    # Only keys, targets and population covariates are needed to recompute polls.
    required = ["municipality_id", "vote_id", "vote_key", "vote_date", "yes_share",
                "statpop_pop_total", "statpop_share_foreign", "statpop_share_0_19"]
    data = pd.read_parquet(input_dir / "dataset.parquet", columns=required,
                           filters=[("vote_date", "<", pd.Timestamp("2023-01-01")),
                                    ("vote_date", ">=", pd.Timestamp("1990-01-01"))])
    expanded, poll_audit = add_poll_features(data, combined)
    data, _ = add_poll_features(data, base)
    # Publication gates and trend chronology are enforced by the shared V2 code.
    records, all_object_scores = [], []
    variants = campaign["plan"]["polling_variants"]
    for variant in variants:
        config_name = variant["structure"]
        pred_path = campaign_dir / (config_name + "_predictions.parquet")
        expected = next(r for r in campaign["runs"] if r["name"] == config_name)
        if sha(pred_path) != expected["predictions_sha256"]:
            raise ValueError("Cached structural predictions changed since their evaluation")
        fixed = CachedPredictionModel(pd.read_parquet(pred_path))
        dataset = expanded if variant["collection"] == "expanded" else data
        tables = []
        for window in campaign["plan"]["validation_windows"]:
            train = dataset[dataset.vote_date.lt(window["start"])]
            evaluation = dataset[dataset.vote_date.between(window["start"], window["end"])].copy()
            params = dict(campaign["plan"]["frozen_poll_parameters"])
            params["trend_factor"] = variant["trend_factor"]
            anchor = PollAnchoredRegressor(fixed, **params).fit(train)
            prediction = anchor.predict(evaluation.drop(columns=["yes_share"]))
            p = evaluation[["municipality_id", "vote_id", "vote_date", "yes_share"]].copy()
            p["prediction"] = prediction
            p["poll_available"] = evaluation.poll_available.to_numpy()
            p["window"] = window["name"]
            tables.append(p)
        result = pd.concat(tables, ignore_index=True)
        score, objects, dates = metrics(result)
        objects["name"] = variant["name"]
        all_object_scores.append(objects)
        result.to_parquet(output / (variant["name"] + "_predictions.parquet"), index=False)
        records.append({**variant, "metrics": score,
                        "polled_objects": int(result[result.poll_available.eq(1)].vote_id.nunique()),
                        "predictions_sha256": sha(output / (variant["name"] + "_predictions.parquet"))})
        print(f"{variant['name']}: {score['macro_object_mae_pp']:.4f} pp", flush=True)
    pd.concat(all_object_scores, ignore_index=True).to_csv(output / "polling_by_object.csv", index=False)
    write_json(output / "polling_comparison.json", {
        "status": "complete", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "historical_polls_sha256": sha(historical_polls), "historical_poll_rows": len(historical),
        "original_polls_sha256": sha(ROOT / "data/external/polls/srg_gfs_polls.csv"),
        "campaign_sha256": sha(campaign_dir / "campaign.json"), "code": _code_evidence(),
        "plan_sha256": campaign["plan_sha256"], "source_audit": poll_audit, "runs": records,
        "strict_forecast_ready": False, "comparison_targets_loaded": False,
        "structural_models_retrained": False, "evaluation_end": "2022-12-31",
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["structure", "polls"])
    parser.add_argument("--input", type=Path, default=ROOT / "reports/generated/municipal_v3_base")
    parser.add_argument("--extra", type=Path, default=ROOT / "data/processed/municipal_v3")
    parser.add_argument("--plan", type=Path, default=PLAN_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--campaign", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--historical-polls", type=Path, default=ROOT / "data/external/polls_historical_v3/polls.csv")
    args = parser.parse_args()
    if args.command == "structure":
        run(args.input, args.extra, args.output, args.plan)
    else:
        polling_comparison(args.input, args.campaign, args.historical_polls, args.output)


if __name__ == "__main__":
    main()

"""Search, freeze and retrospective comparison for municipal_v2 experiments."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from scripts.modeling.municipal_v2 import (
    DEFAULT_OUTPUT,
    KEYS,
    PROTOCOL,
    SEED,
    code_hashes,
    digest,
    environment,
    fit_model,
    freeze_history,
    leaderboard,
    metrics,
    read_data,
    run_trial,
    write_json,
)


def tune(output, trials, study_name, family="xgboost"):
    import optuna

    output = Path(output)
    data, manifest = read_data(output)
    protocol = json.loads(PROTOCOL.read_text())
    data = data.loc[data.vote_date.lt(protocol["comparison_start"])].copy()
    signature = hashlib.sha256(json.dumps({"data": manifest["dataset_sha256"],
                                          "code": code_hashes(), "environment": environment(),
                                          "data_manifest": digest(output / "data_manifest.json")},
                                         sort_keys=True).encode()).hexdigest()
    study = optuna.create_study(study_name=study_name,
        storage=f"sqlite:///{(output / 'optuna.sqlite3').resolve()}", load_if_exists=True,
        direction="minimize", sampler=optuna.samplers.TPESampler(seed=SEED))
    if study.user_attrs.get("signature", signature) != signature:
        raise ValueError("Study source/code signature changed; create a new study")
    study.set_user_attr("signature", signature)
    study.set_user_attr("metric", "macro_object_mae_pp")

    def objective(trial):
        config = {"name": f"{study_name}_{trial.number:03d}", "model": family,
                  "blocks": trial.suggest_categorical("blocks", ["political", "direction"]),
                  "train_start": trial.suggest_categorical("train_start", ["1981-01-01", "1990-01-01", "2000-01-01", "2012-01-01"])}
        if family == "xgboost":
            config["select_k"] = trial.suggest_categorical("select_k", ["all", 64, 128])
            config["half_life_years"] = trial.suggest_categorical("half_life_years", [None, 8., 16.])
            config["params"] = {
                "n_estimators": trial.suggest_int("n_estimators", 150, 550, step=100),
                "max_depth": trial.suggest_int("max_depth", 2, 5),
                "learning_rate": trial.suggest_float("learning_rate", .025, .1, log=True),
                "min_child_weight": trial.suggest_categorical("min_child_weight", [20., 100., 400.]),
                "reg_lambda": trial.suggest_float("reg_lambda", 2., 100., log=True),
                "reg_alpha": trial.suggest_categorical("reg_alpha", [0., 1., 10.]),
                "subsample": 1., "colsample_bytree": 1.,
                "objective": trial.suggest_categorical("objective", ["reg:squarederror", "reg:absoluteerror"])}
        elif family == "profile":
            config["params"] = {
                "dimensions": trial.suggest_categorical("dimensions", [0, 2, 3, 5, 8]),
                "model": trial.suggest_categorical("mapping", ["ridge", "extra_trees", "xgboost"]),
                "alpha": trial.suggest_float("alpha", 1., 1000., log=True),
                "n_estimators": 300,
                "max_depth": trial.suggest_int("max_depth", 2, 6),
                "min_samples_leaf": trial.suggest_int("min_samples_leaf", 2, 12),
                "reg_lambda": trial.suggest_float("reg_lambda", 1., 30., log=True),
                "random_state": SEED}
        else:
            raise ValueError("Search supports xgboost or profile")
        result = run_trial(config, data, manifest, protocol, output,
            hypothesis="Sequential search using only expanding chronological validation; every configuration is recorded")
        trial.set_user_attr("run_id", result["run_id"])
        trial.set_user_attr("fold_scores", {f["name"]: f["metrics"]["macro_object_mae_pp"] for f in result["folds"]})
        leaderboard(output)
        return result["metrics"]["macro_object_mae_pp"]

    study.optimize(objective, n_trials=trials, gc_after_trial=True)
    print(json.dumps({"best_run_id": study.best_trial.user_attrs["run_id"],
                      "best_macro_object_mae_pp": study.best_value}, indent=2), flush=True)


def freeze(output, run_id):
    output = Path(output)
    _, manifest = read_data(output)
    selected = json.loads((output / "trials" / run_id / "trial.json").read_text())
    if selected["status"] != "complete" or selected["data_sha256"] != manifest["dataset_sha256"]:
        raise ValueError("Only a complete matching development trial can be frozen")
    if selected["code"] != code_hashes():
        raise ValueError("Implementation changed since this trial; rerun the chosen configuration with a new name")
    if selected["environment"] != environment():
        raise ValueError("Environment changed since the selected trial")
    if selected["data_manifest_sha256"] != digest(output / "data_manifest.json"):
        raise ValueError("Data manifest changed since the selected trial")
    current_protocol = json.loads(PROTOCOL.read_text())
    if selected.get("protocol") != current_protocol:
        raise ValueError("Selected trial used a different actual protocol")
    frozen = {"selected_run_id": run_id, "configuration": selected["configuration"],
              "development_metrics": selected["metrics"], "protocol": json.loads(PROTOCOL.read_text()),
              "data_sha256": manifest["dataset_sha256"], "sources": manifest["sources"],
              "data_manifest_sha256": digest(output / "data_manifest.json"),
              "code": code_hashes(), "environment": environment(),
              "comparison_is_independent": False,
              "comparison_explanation": "2023-2025 outcomes were already consulted in prior project experiments",
              "strict_forecast_ready": False}
    canonical = json.dumps(frozen, sort_keys=True, default=str)
    frozen["signature"] = hashlib.sha256(canonical.encode()).hexdigest()
    path = output / "frozen_selection.json"
    if path.exists():
        raise FileExistsError("A selection is already frozen; preserve it and use a new experiment directory")
    write_json(path, frozen)
    print(f"FROZEN {run_id}", flush=True)


def verify_freeze(output):
    output = Path(output)
    frozen = json.loads((output / "frozen_selection.json").read_text())
    unsigned = {k: v for k, v in frozen.items() if k != "signature"}
    expected = hashlib.sha256(json.dumps(unsigned, sort_keys=True, default=str).encode()).hexdigest()
    if frozen["signature"] != expected:
        raise ValueError("Frozen configuration integrity failure")
    data, manifest = read_data(output)
    if frozen["data_sha256"] != manifest["dataset_sha256"] or frozen["code"] != code_hashes():
        raise ValueError("Frozen code or data changed")
    if frozen["environment"] != environment():
        raise ValueError("Frozen environment changed")
    if frozen["data_manifest_sha256"] != digest(output / "data_manifest.json"):
        raise ValueError("Frozen data manifest changed")
    return frozen, data, manifest


def date_bootstrap(predictions, replicates=2000):
    """Resample whole dates; score stays an equal-object mean, not a row bootstrap."""
    _, objects, _ = metrics(predictions)
    grouped = [group.mae_pp.to_numpy() for _, group in objects.groupby("vote_date")]
    if len(grouped) < 2:
        return {"status": "insufficient_dates"}
    rng = np.random.default_rng(SEED)
    samples = [np.concatenate([grouped[i] for i in rng.integers(0, len(grouped), len(grouped))]).mean()
               for _ in range(replicates)]
    return {"status": "descriptive_cluster_bootstrap", "lower_95_pp": float(np.quantile(samples, .025)),
            "upper_95_pp": float(np.quantile(samples, .975)), "replicates": replicates,
            "unit": "whole voting date", "dates": len(grouped),
            "limit": "Does not undo prior test exposure, selection optimism, or vintage uncertainty"}


def compare(output):
    output = Path(output)
    frozen, data, manifest = verify_freeze(output)
    destination = output / "comparison"
    if (destination / "summary.json").exists():
        raise FileExistsError("Comparison already opened; reuse the recorded result instead of rerunning selection")
    destination.mkdir(parents=True, exist_ok=True)
    status_path = destination / "status.json"
    if status_path.exists():
        previous = json.loads(status_path.read_text())
        if previous["frozen_signature"] != frozen["signature"]:
            raise ValueError("An interrupted comparison belongs to a different frozen experiment")
    write_json(status_path, {"status": "running", "frozen_signature": frozen["signature"]})
    protocol = frozen["protocol"]
    config = frozen["configuration"]
    train = data.loc[data.vote_date.ge(config.get("train_start", "2012-01-01"))
                     & data.vote_date.lt(protocol["comparison_start"])].copy()
    evaluation = data.loc[data.vote_date.between(protocol["comparison_start"], protocol["comparison_end"])].copy()
    evaluation = freeze_history(train, evaluation)
    start = time.monotonic()
    with threadpool_limits(limits=2):
        model = fit_model(train, config, manifest)
        predicted = model.predict(evaluation)
    rows = evaluation[KEYS + ["vote_date", "canton", "yes_share"]].copy()
    rows["prediction"] = predicted
    scored, objects, dates = metrics(rows)
    rows.to_parquet(destination / "predictions.parquet", index=False)
    objects.to_csv(destination / "by_object.csv", index=False)
    dates.to_csv(destination / "by_date.csv", index=False)
    # These references were specified before opening this comparison.
    references = {}
    for family in ("constant", "history"):
        baseline = fit_model(train, {"name": family, "model": family}, manifest)
        copy = rows.copy()
        copy["prediction"] = baseline.predict(evaluation)
        references[family] = metrics(copy)[0]
    row_errors = rows.assign(absolute_error_pp=(rows.yes_share - rows.prediction).abs() * 100)
    row_errors.groupby("canton").absolute_error_pp.agg(["mean", "count"]).to_csv(destination / "by_canton.csv")
    summary = {"selected_run_id": frozen["selected_run_id"], "metrics": scored,
        "reference_metrics": references, "uncertainty": date_bootstrap(rows),
        "goal_4pp_observed": scored["macro_object_mae_pp"] <= 4.,
        "comparison_is_independent": False, "strict_forecast_ready": False,
        "train_rows": len(train), "train_objects": int(train.vote_id.nunique()),
        "frozen_signature": frozen["signature"], "elapsed_seconds": time.monotonic() - start}
    joblib.dump(model, destination / "evaluated_model.joblib", compress=3)
    write_json(destination / "summary.json", summary)
    write_json(status_path, {"status": "complete", "frozen_signature": frozen["signature"]})
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def fit_candidate(output):
    """Refit selected settings on all definitive historical rows after evaluation.

    This candidate has no new evaluated accuracy; the frozen retrospective model
    and its predictions remain separate and unchanged.
    """
    output = Path(output)
    frozen, data, manifest = verify_freeze(output)
    if not (output / "comparison/summary.json").exists():
        raise ValueError("Record the frozen comparison before fitting the reusable candidate")
    config = frozen["configuration"]
    train = data.loc[data.vote_date.ge(config.get("train_start", "2012-01-01"))].copy()
    with threadpool_limits(limits=2):
        model = fit_model(train, config, manifest)
    path = output / "candidate_model.joblib"
    joblib.dump(model, path, compress=3)
    if hasattr(model.model, "save_model"):
        model.model.save_model(str(output / "candidate_model.cbm"))
    card = {"configuration": config, "selection": frozen["selected_run_id"],
        "training_end": str(train.vote_date.max().date()), "training_start": str(train.vote_date.min().date()),
        "training_rows": len(train), "training_objects": int(train.vote_id.nunique()),
        "model_sha256": digest(path), "features": model.numeric + model.categorical,
        "strict_forecast_ready": False, "mode": manifest["mode"],
        "input_contract": "Prepared municipality-object features with audited correspondence; no outcome needed for predict. Poll anchoring and centered residuals require a complete municipal population batch for each object",
        "limitation": "Research candidate; historical vintages unverified, title directions are conservative proxies. Performance of the all-data refit is not separately measured",
        "environment": environment(), "frozen_signature": frozen["signature"]}
    write_json(output / "candidate_model_card.json", card)
    # Verify the actual serialized object on target-free inputs.
    sample = train.loc[train.vote_id.eq(train.vote_id.iloc[-1])].drop(columns="yes_share")
    reloaded = joblib.load(path)
    np.testing.assert_allclose(model.predict(sample), reloaded.predict(sample), rtol=0, atol=1e-12)
    print(json.dumps(card, ensure_ascii=False, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["tune", "freeze", "compare", "fit"])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--trials", type=int, default=12)
    parser.add_argument("--study-name", default="xgb_search_v1")
    parser.add_argument("--family", choices=["xgboost", "profile"], default="xgboost")
    parser.add_argument("--run-id")
    args = parser.parse_args()
    if args.stage == "tune":
        tune(args.output, args.trials, args.study_name, args.family)
    elif args.stage == "freeze":
        if not args.run_id:
            raise ValueError("freeze needs --run-id")
        freeze(args.output, args.run_id)
    elif args.stage == "compare":
        compare(args.output)
    else:
        fit_candidate(args.output)


if __name__ == "__main__":
    main()

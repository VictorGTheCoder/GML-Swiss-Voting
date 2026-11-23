"""Reproducible retrospective experiments for genuinely new voting objects.

The existing strict forecast evaluator is deliberately untouched. This module
uses source snapshots whose historical publication evidence is incomplete.
Run ``python -m scripts.modeling.municipal_v2 --help`` for the staged CLI.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import platform
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.feature_selection import SelectKBest, f_regression
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits

from scripts.common.config import ROOT
from scripts.integration.build_modeling_dataset import SOURCES, build

SEED = 20261123
DEFAULT_OUTPUT = ROOT / "reports/generated/municipal_v2"
PROTOCOL = ROOT / "experiments/municipal_v2/protocol.json"
KEYS = ["municipality_id", "vote_id"]
BASE_NUMERIC = ["history_mean_yes", "history_n_objects", "log_population",
                "statpop_share_foreign", "statpop_share_0_19", "statpop_share_20_39",
                "statpop_share_40_64", "statpop_share_65_plus", "statpop_mean_age"]
BASE_NUMERIC += [f"party_share_{p}" for p in
                 ["plr", "pdc", "ps", "udc", "pev", "verts", "pvl", "pbd", "centre"]]
BASE_CATEGORICAL = ["canton", "urban_rural", "language_region", "object_legal_form",
                    "object_domain_1", "object_domain_2", "object_domain_3"]
FORBIDDEN = {"yes_share", "target_share", "votes_yes", "votes_no", "turnout",
             "eligible_voters", "valid_ballots", "ballots_cast", "vote_id",
             "vote_key", "municipality_id", "volkja-proz", "annahme"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    default=str, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def source_hashes():
    return {name: {"path": f"data/processed/{relative}",
                   "sha256": digest(ROOT / "data/processed" / relative)}
            for name, relative in SOURCES.items()}


def code_hashes():
    paths = [Path(__file__), PROTOCOL,
             ROOT / "scripts/integration/build_modeling_dataset.py",
             ROOT / "scripts/modeling/residual_voting_model.py",
             ROOT / "scripts/modeling/poll_anchor.py"]
    paths += sorted((ROOT / "scripts/modeling").glob("*_v2.py"))
    return {str(p.relative_to(ROOT)): digest(p) for p in dict.fromkeys(paths) if p.is_file()}


def environment():
    import catboost
    import optuna
    import xgboost
    return {"python": platform.python_version(), "numpy": np.__version__,
            "pandas": pd.__version__, "sklearn": sklearn.__version__,
            "xgboost": xgboost.__version__, "catboost": catboost.__version__,
            "optuna": optuna.__version__}


def prepare(output):
    """Reuse audited joins; extend outcomes, never backfill future demographics."""
    from scripts.modeling.direction_features_v2 import add_direction_features
    from scripts.modeling.political_features_v2 import add_political_features

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    frames = {name: pd.read_parquet(ROOT / "data/processed" / relative)
              for name, relative in SOURCES.items()}
    table, audit = build(frames, start="1981-01-01")
    table["log_population"] = np.log1p(table.statpop_pop_total.astype(float))
    table, political = add_political_features(table, frames["swissvotes"])
    table, direction = add_direction_features(table, frames["swissvotes"])
    polls = None
    poll_path = ROOT / "data/external/polls/srg_gfs_polls.csv"
    if poll_path.exists():
        from scripts.modeling.poll_anchor import add_poll_features
        table, polls = add_poll_features(table, pd.read_csv(poll_path, dtype={"vote_key": "string"}))
        polls["path"] = str(poll_path.relative_to(ROOT))
        polls["sha256"] = digest(poll_path)
    if table.duplicated(KEYS).any() or not table.yes_share.between(0, 1).all():
        raise ValueError("Invalid target or duplicate municipal-object observations")
    if table.vote_date.max() >= pd.Timestamp("2026-01-01"):
        raise ValueError("Unreviewed 2026 outcomes cannot enter this experiment")
    table.to_parquet(output / "dataset.parquet", index=False)
    manifest = {"mode": "retrospective_fixed_2026_geography",
                "strict_forecast_ready": False, "sources": source_hashes(),
                "dataset_sha256": digest(output / "dataset.parquet"),
                "audit": audit, "political": political, "direction": direction, "polls": polls,
                "baseline_numeric": BASE_NUMERIC, "baseline_categorical": BASE_CATEGORICAL,
                "rows": len(table), "objects": int(table.vote_id.nunique()),
                "dates": int(table.vote_date.nunique()),
                "first_date": str(table.vote_date.min().date()),
                "last_date": str(table.vote_date.max().date())}
    write_json(output / "data_manifest.json", manifest)
    coverage = table.groupby(table.vote_date.dt.year).agg(
        rows=("vote_id", "size"), objects=("vote_id", "nunique"),
        dates=("vote_date", "nunique"), missing_population=("log_population", lambda s: s.isna().mean()),
        missing_elections=("elections_missing", "mean"))
    coverage.to_csv(output / "coverage_by_year.csv")
    print(json.dumps({k: manifest[k] for k in ["rows", "objects", "dates", "first_date", "last_date"]}), flush=True)


def read_data(output):
    output = Path(output)
    manifest = json.loads((output / "data_manifest.json").read_text())
    if digest(output / "dataset.parquet") != manifest["dataset_sha256"]:
        raise ValueError("Prepared dataset changed; rebuild and declare a new experiment")
    if source_hashes() != manifest["sources"]:
        raise ValueError("Sources changed since preparation")
    if manifest.get("polls") and digest(ROOT / manifest["polls"]["path"]) != manifest["polls"]["sha256"]:
        raise ValueError("Poll snapshot changed since preparation")
    return pd.read_parquet(output / "dataset.parquet"), manifest


def feature_columns(config, manifest):
    numeric, categorical = list(BASE_NUMERIC), list(BASE_CATEGORICAL)
    blocks = config.get("blocks", "base")
    if blocks in ("political", "direction"):
        numeric += manifest["political"]["numeric_features"]
        categorical += manifest["political"].get("categorical_features", [])
    if blocks == "direction":
        numeric += manifest["direction"]["numeric_features"]
        categorical += manifest["direction"].get("categorical_features", [])
    if config.get("drop_demographics"):
        numeric = [c for c in numeric if not c.startswith("statpop_") and c != "log_population"]
    if config.get("drop_history"):
        numeric = [c for c in numeric if not c.startswith("history_")]
    numeric, categorical = list(dict.fromkeys(numeric)), list(dict.fromkeys(categorical))
    if set(numeric + categorical) & FORBIDDEN:
        raise ValueError("Outcome or identifier attempted to enter predictors")
    return numeric, categorical


def freeze_history(train, evaluation):
    """Use the latest training-date historical sums, including that date's objects.

    The prepared history includes pre-1981 context. Evaluation targets are never
    read here. Multiple objects on the last training date are aggregated together.
    """
    if train.empty or train.vote_date.max() >= evaluation.vote_date.min():
        raise ValueError("All training dates must precede every evaluation date")
    recent = train.loc[train.vote_date.eq(train.groupby("municipality_id").vote_date.transform("max"))]
    records = []
    for municipality, group in recent.groupby("municipality_id", sort=False):
        first = group.iloc[0]
        old_n = float(first.history_n_objects)
        old_mean = float(first.history_mean_yes) if pd.notna(first.history_mean_yes) else 0.
        n = old_n + len(group)
        total = old_mean * old_n + group.yes_share.astype(float).sum()
        records.append((municipality, total / n, n))
    known = pd.DataFrame(records, columns=["municipality_id", "history_mean_yes", "history_n_objects"])
    result = evaluation.drop(columns=["history_mean_yes", "history_n_objects"]).merge(
        known, on="municipality_id", how="left", validate="many_to_one", sort=False)
    result.index = evaluation.index
    return result


def windows(data, protocol, train_start):
    for definition in protocol["validation_windows"]:
        start, end = pd.Timestamp(definition["start"]), pd.Timestamp(definition["end"])
        train = data.loc[data.vote_date.ge(train_start) & data.vote_date.lt(start)].copy()
        evaluation = data.loc[data.vote_date.between(start, end)].copy()
        if train.empty or evaluation.empty:
            raise ValueError(f"Empty declared window {definition['name']}")
        yield definition["name"], train, freeze_history(train, evaluation)


def training_weights(train, config):
    counts = train.groupby("vote_id").vote_id.transform("size").to_numpy(float)
    weights = 1. / counts
    half_life = config.get("half_life_years")
    if half_life is not None:
        if half_life <= 0:
            raise ValueError("half_life_years must be positive")
        age = (train.vote_date.max() - train.vote_date).dt.days.to_numpy() / 365.25
        weights *= np.exp2(-age / half_life)
    return weights / weights.mean()


class SafeSelectKBest(TransformerMixin, BaseEstimator):
    """Cap k using only the training feature count; expose selected feature names."""
    def __init__(self, k="all"):
        self.k = k

    def fit(self, x, y):
        k = "all" if self.k == "all" else min(int(self.k), x.shape[1])
        if k != "all" and k <= 0:
            raise ValueError("SelectKBest k must be positive or all")
        self.n_features_in_ = x.shape[1]
        self.selector_ = None if k == "all" else SelectKBest(f_regression, k=k).fit(x, y)
        return self

    def transform(self, x):
        return x if self.selector_ is None else self.selector_.transform(x)

    def get_feature_names_out(self, input_features=None):
        if self.selector_ is None:
            return np.asarray(input_features if input_features is not None
                              else [f"x{i}" for i in range(self.n_features_in_)], dtype=object)
        return self.selector_.get_feature_names_out(input_features)


def model_frame(frame, numeric, categorical, *, catboost=False):
    result = frame[numeric + categorical].copy()
    for column in numeric:
        result[column] = pd.to_numeric(result[column], errors="coerce").astype(float)
        if np.isinf(result[column]).any():
            raise ValueError(f"Infinite predictor {column}")
    for column in categorical:
        result[column] = result[column].astype("string").fillna("__missing__").astype(object)
    return result


@dataclass
class FittedModel:
    model: object
    numeric: list
    categorical: list
    kind: str
    config: dict
    selected_features: list

    def predict(self, frame):
        if self.kind == "constant":
            return np.full(len(frame), self.model)
        if self.kind == "history":
            return frame.history_mean_yes.fillna(self.model).to_numpy(float)
        if self.kind in ("profile", "hierarchical", "poll_anchor"):
            return np.clip(self.model.predict(frame), 0, 1)
        matrix = model_frame(frame, self.numeric, self.categorical)
        return np.clip(self.model.predict(matrix), 0, 1)


def validate_config(config):
    """Reject settings that an estimator would silently ignore."""
    kind = config["model"]
    if config.get("blocks", "base") not in {"base", "political", "direction"}:
        raise ValueError("Unknown feature block")
    if kind not in {"ridge", "xgboost"} and config.get("select_k", "all") != "all":
        raise ValueError(f"select_k is not implemented for {kind}")
    if kind in {"profile", "hierarchical", "poll_anchor"} and config.get("half_life_years") is not None:
        raise ValueError(f"half_life_years is not implemented for {kind}")
    if kind == "poll_anchor":
        base = config["base"]
        validate_config(base)
        if pd.Timestamp(config.get("train_start", "2012-01-01")) > pd.Timestamp(base.get("train_start", "2012-01-01")):
            raise ValueError("poll_anchor train_start would truncate the declared base training history")


def fit_model(train, config, manifest):
    validate_config(config)
    kind = config["model"]
    numeric, categorical = feature_columns(config, manifest)
    y = train.yes_share.to_numpy(float)
    weights = training_weights(train, config)
    fallback = float(train.groupby("vote_id").yes_share.mean().mean())
    if kind in ("constant", "history"):
        return FittedModel(fallback, [], [], kind, config, [])
    if kind == "poll_anchor":
        from scripts.modeling.poll_anchor import PollAnchoredRegressor
        base_config = config["base"]
        base_train = train.loc[train.vote_date.ge(base_config.get("train_start", "2012-01-01"))]
        base_model = fit_model(base_train, base_config, manifest)
        model = PollAnchoredRegressor(base_model=base_model, **config.get("params", {})).fit(base_train)
        poll_numeric = ["poll_yes_share", "poll_no_share", "poll_undecided_share",
                        "poll_available", "poll_population_weight"]
        return FittedModel(model, base_model.numeric + poll_numeric, base_model.categorical,
                           kind, config, base_model.selected_features + poll_numeric)
    if kind in ("profile", "hierarchical"):
        from scripts.modeling.object_profile_v2 import ObjectProfileRegressor
        # Object scope comes from explicit source contracts, not incidental
        # constancy of a local feature in one training sample.
        obj_numeric = [c for c in manifest["political"]["object_numeric_features"] if c in numeric]
        obj_numeric += [c for c in manifest["direction"]["numeric_features"] if c in numeric]
        obj_cat = [c for c in categorical if c.startswith("object_")]
        obj_cat += [c for c in manifest["political"]["object_categorical_features"] if c in categorical]
        if kind == "profile":
            model = ObjectProfileRegressor(object_features_numeric=obj_numeric,
                object_features_categorical=obj_cat, **config.get("params", {}))
        else:
            from scripts.modeling.residual_voting_model import HierarchicalResidualRegressor
            model = HierarchicalResidualRegressor(object_features_numeric=obj_numeric,
                object_features_categorical=obj_cat, local_numeric=numeric,
                local_categorical=categorical, **config.get("params", {}))
        model.fit(train)
        selected = obj_numeric + obj_cat if kind == "profile" else numeric + categorical
        return FittedModel(model, obj_numeric if kind == "profile" else numeric,
                           obj_cat if kind == "profile" else categorical, kind, config, selected)
    x = model_frame(train, numeric, categorical)
    params = config.get("params", {})
    if kind == "catboost":
        from catboost import CatBoostRegressor
        model = CatBoostRegressor(random_seed=SEED, thread_count=2, verbose=False,
            allow_writing_files=False, has_time=True, **params)
        model.fit(x, y, sample_weight=weights, cat_features=categorical)
        return FittedModel(model, numeric, categorical, kind, config, numeric + categorical)
    transforms = [("numeric", Pipeline([
        ("impute", SimpleImputer(strategy="median", keep_empty_features=True, add_indicator=True)),
        ("scale", StandardScaler())]), numeric),
        ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=True), categorical)]
    preprocess = ColumnTransformer(transforms, sparse_threshold=1.)
    if kind == "ridge":
        estimator = Ridge(solver="lsqr", tol=1e-5, **params)
    elif kind == "xgboost":
        from xgboost import XGBRegressor
        estimator = XGBRegressor(tree_method="hist", random_state=SEED, n_jobs=2,
                                  eval_metric="mae", **params)
    else:
        raise ValueError(f"Unknown model family {kind}")
    pipeline = Pipeline([("prepare", preprocess),
                         ("select", SafeSelectKBest(config.get("select_k", "all"))),
                         ("model", estimator)])
    pipeline.fit(x, y, model__sample_weight=weights)
    names = pipeline.named_steps["prepare"].get_feature_names_out()
    selected = pipeline.named_steps["select"].get_feature_names_out(names).tolist()
    return FittedModel(pipeline, numeric, categorical, kind, config, selected)


def metrics(predictions):
    frame = predictions.copy()
    if frame.empty or frame[KEYS].isna().any().any() or frame.duplicated(KEYS).any():
        raise ValueError("Metrics require nonempty unique municipality-object keys")
    values = frame[["yes_share", "prediction"]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or ((values < 0) | (values > 1)).any():
        raise ValueError("Metrics require finite target and prediction shares in [0, 1]")
    frame["absolute_error_pp"] = 100 * (frame.yes_share - frame.prediction).abs()
    objects = frame.groupby(["vote_id", "vote_date"], as_index=False).agg(
        mae_pp=("absolute_error_pp", "mean"), n_communes=("municipality_id", "size"),
        observed_mean=("yes_share", "mean"), predicted_mean=("prediction", "mean"))
    dates = objects.groupby("vote_date", as_index=False).agg(mae_pp=("mae_pp", "mean"), objects=("vote_id", "size"))
    return {"macro_object_mae_pp": float(objects.mae_pp.mean()),
            "row_mae_pp": float(frame.absolute_error_pp.mean()),
            "macro_date_mae_pp": float(dates.mae_pp.mean()),
            "median_row_ae_pp": float(frame.absolute_error_pp.median()),
            "p90_row_ae_pp": float(frame.absolute_error_pp.quantile(.9)),
            "within_4pp_share": float(frame.absolute_error_pp.le(4).mean()),
            "majority_accuracy": float((frame.yes_share.gt(.5) == frame.prediction.gt(.5)).mean()),
            "rows": len(frame), "objects": len(objects), "dates": len(dates)}, objects, dates


def run_trial(config, data, manifest, protocol, output, *, hypothesis=""):
    """Persist successes and failures; every trial has its complete configuration."""
    output = Path(output)
    config_json = json.dumps(config, sort_keys=True)
    protocol_hash = hashlib.sha256(json.dumps(protocol, sort_keys=True).encode()).hexdigest()
    run_id = config["name"] + "-" + hashlib.sha256(config_json.encode()).hexdigest()[:10]
    folder = output / "trials" / run_id
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "trial.json").exists():
        prior = json.loads((folder / "trial.json").read_text())
        if (prior["data_sha256"] == manifest["dataset_sha256"] and prior["status"] == "complete"
                and prior["code"] == code_hashes() and prior["environment"] == environment()
                and prior.get("protocol_sha256") == protocol_hash
                and prior["data_manifest_sha256"] == digest(output / "data_manifest.json")):
            print(f"CACHED {run_id} {prior['metrics']['macro_object_mae_pp']:.4f} pp", flush=True)
            return prior
        raise ValueError(f"Existing run {run_id} has different provenance or failed; use a new run name")
    started = time.monotonic()
    record = {"run_id": run_id, "configuration": config, "hypothesis": hypothesis,
              "data_sha256": manifest["dataset_sha256"],
              "data_manifest_sha256": digest(output / "data_manifest.json"), "code": code_hashes(),
              "protocol": protocol, "protocol_sha256": protocol_hash,
              "environment": environment(), "status": "running", "mode": manifest["mode"],
              "strict_forecast_ready": False, "folds": []}
    write_json(folder / "trial.json", record)
    all_predictions = []
    try:
        for name, train, evaluation in windows(data, protocol, pd.Timestamp(config.get("train_start", "2012-01-01"))):
            with threadpool_limits(limits=2):
                model = fit_model(train, config, manifest)
                values = model.predict(evaluation)
            if not np.isfinite(values).all():
                raise ValueError("Nonfinite predictions")
            prediction = evaluation[KEYS + ["vote_date", "canton", "yes_share"]].copy()
            prediction["prediction"] = values
            prediction["window"] = name
            scored, _, _ = metrics(prediction)
            record["folds"].append({"name": name, "train_rows": len(train),
                "train_objects": int(train.vote_id.nunique()),
                "training_dates": sorted(train.vote_date.dt.strftime("%Y-%m-%d").unique().tolist()),
                "evaluation_dates": sorted(evaluation.vote_date.dt.strftime("%Y-%m-%d").unique().tolist()),
                "metrics": scored, "selected_features": model.selected_features})
            all_predictions.append(prediction)
            print(f"{run_id} {name}: {scored['macro_object_mae_pp']:.4f} pp; {len(model.selected_features)} features", flush=True)
            write_json(folder / "trial.json", record)
            del model, train, evaluation
            gc.collect()
        predictions = pd.concat(all_predictions, ignore_index=True)
        record["metrics"], objects, dates = metrics(predictions)
        predictions.to_parquet(folder / "predictions.parquet", index=False)
        objects.to_csv(folder / "by_object.csv", index=False)
        dates.to_csv(folder / "by_date.csv", index=False)
        record["status"] = "complete"
        record["goal_reached_on_development"] = record["metrics"]["macro_object_mae_pp"] <= protocol["goal_mae_pp"]
    except Exception as error:
        record["status"] = "failed"
        record["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        record["elapsed_seconds"] = time.monotonic() - started
        write_json(folder / "trial.json", record)
    print(f"COMPLETE {run_id}: {record['metrics']['macro_object_mae_pp']:.4f} pp, {record['elapsed_seconds']:.1f}s", flush=True)
    return record


def baseline_configs():
    configs = [{"name": "constant", "model": "constant"},
               {"name": "municipal_history", "model": "history"}]
    xgb = {"n_estimators": 300, "max_depth": 3, "learning_rate": .04,
           "min_child_weight": 200, "reg_lambda": 20., "reg_alpha": 0.,
           "subsample": 1., "colsample_bytree": 1., "objective": "reg:squarederror"}
    cat = {"iterations": 400, "depth": 4, "learning_rate": .04,
           "l2_leaf_reg": 20., "loss_function": "RMSE"}
    for blocks in ("base", "political", "direction"):
        for family, params in [("ridge", {"alpha": 1000.}), ("xgboost", xgb), ("catboost", cat)]:
            configs.append({"name": f"{family}_{blocks}_recent", "model": family,
                            "blocks": blocks, "params": params, "train_start": "2012-01-01"})
    for start in ("1990-01-01", "2000-01-01"):
        configs.append({"name": f"xgboost_political_since_{start[:4]}", "model": "xgboost",
                        "blocks": "political", "params": xgb, "train_start": start})
    return configs


def leaderboard(output):
    records = []
    current_code, current_environment = code_hashes(), environment()
    manifest_path = Path(output) / "data_manifest.json"
    manifest_hash = digest(manifest_path) if manifest_path.exists() else None
    for path in sorted((Path(output) / "trials").glob("*/trial.json")):
        trial = json.loads(path.read_text())
        if trial["status"] == "complete":
            records.append({"run_id": trial["run_id"], "model": trial["configuration"]["model"],
                "blocks": trial["configuration"].get("blocks", "base"),
                "train_start": trial["configuration"].get("train_start", "2012-01-01"),
                "current_provenance": trial["code"] == current_code and trial["environment"] == current_environment
                    and trial.get("data_manifest_sha256") == manifest_hash,
                **trial["metrics"], "elapsed_seconds": trial["elapsed_seconds"]})
    result = pd.DataFrame(records).sort_values(["macro_object_mae_pp", "run_id"])
    result.to_csv(Path(output) / "leaderboard.csv", index=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "baseline", "run", "leaderboard"])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--hypothesis", default="")
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare(args.output)
        return
    if args.stage == "leaderboard":
        print(leaderboard(args.output).to_string(index=False))
        return
    data, manifest = read_data(args.output)
    protocol = json.loads(PROTOCOL.read_text())
    # Candidate selection never receives the previously exposed comparison rows.
    data = data.loc[data.vote_date.lt(protocol["comparison_start"])].copy()
    configs = baseline_configs() if args.stage == "baseline" else json.loads(args.config.read_text())
    if isinstance(configs, dict):
        configs = [configs]
    for config in configs:
        run_trial(config, data, manifest, protocol, args.output, hypothesis=args.hypothesis)
        leaderboard(args.output)


if __name__ == "__main__":
    main()

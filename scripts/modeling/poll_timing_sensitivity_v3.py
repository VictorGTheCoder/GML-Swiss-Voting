"""Declared endpoint sensitivity for approximate historical poll midpoints.

Reuse frozen structural predictions and polling parameters. The four scenarios
move only explicitly approximate historical survey midpoints, simultaneously
to lower/upper bounds for wave 1 and wave 2. Their range is not a confidence
interval or an exhaustive bound over independent choices for every object.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.common.config import ROOT
from scripts.modeling.enrichment_experiment_v3 import CachedPredictionModel
from scripts.modeling.municipal_v2 import metrics, write_json
from scripts.modeling.poll_anchor import PollAnchoredRegressor, add_poll_features

DEFAULT_OUTPUT = ROOT / "reports/datasets/municipal_v3_20261123"
SCENARIOS = [
    {"name": f"wave1_{first}_wave2_{second}", "wave1": first, "wave2": second}
    for first in ("lower", "upper") for second in ("lower", "upper")
]
LIMITATION = (
    "Range of four simultaneous endpoint scenarios, not a confidence interval "
    "or a global bound over independent midpoint choices per object; no scenario "
    "is selected for deployment or used for calibration."
)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def strict_flags(values):
    """Accept boolean literals only; in particular the string False is false."""
    parsed = values.astype("string").str.strip().str.lower().map({"true": True, "false": False})
    if parsed.isna().any():
        raise ValueError("survey_midpoint_is_approximate requires explicit True/False values")
    return parsed.astype(bool)


def scenario_polls(polls, wave1, wave2):
    """Change only survey_midpoint, and only for explicitly approximate rows."""
    if wave1 not in {"lower", "upper"} or wave2 not in {"lower", "upper"}:
        raise ValueError("Midpoint endpoints must be lower or upper")
    result = polls.copy()
    approximate = strict_flags(result.survey_midpoint_is_approximate)
    wave = pd.to_numeric(result.wave, errors="raise")
    if not wave.isin([1, 2]).all():
        raise ValueError("Historical sensitivity requires wave 1 or 2")
    lower = pd.to_datetime(result.survey_midpoint_lower, errors="raise")
    upper = pd.to_datetime(result.survey_midpoint_upper, errors="raise")
    nominal = pd.to_datetime(result.survey_midpoint, errors="raise")
    start = pd.to_datetime(result.survey_start, errors="raise")
    end = pd.to_datetime(result.survey_end, errors="raise")
    invalid = lower.isna() | upper.isna() | nominal.isna() | start.isna() | end.isna()
    invalid |= (lower > nominal) | (nominal > upper) | (lower < start) | (upper > end)
    if invalid.any():
        raise ValueError("Midpoint bounds must contain nominal midpoint and lie inside fieldwork")
    for number, endpoint in [(1, wave1), (2, wave2)]:
        mask = approximate & wave.eq(number)
        result.loc[mask, "survey_midpoint"] = result.loc[mask, f"survey_midpoint_{endpoint}"]
    return result


def validate_windows(windows):
    previous = None
    for window in windows:
        start, end = pd.Timestamp(window["start"]), pd.Timestamp(window["end"])
        if start < pd.Timestamp("1990-01-01") or end >= pd.Timestamp("2023-01-01") or end < start:
            raise ValueError("Sensitivity windows must remain within 1990--2022")
        if previous is not None and start <= previous:
            raise ValueError("Sensitivity windows must be ordered and disjoint")
        previous = end


def _read(path):
    return json.loads(Path(path).read_text())


def _assert_hash(path, expected, label):
    actual = sha(path)
    if actual != expected:
        raise ValueError(f"{label} hash mismatch")
    return actual


def declare(input_dir, campaign_dir, comparison_dir, historical_polls, output):
    """Persist the fixed plan and provenance before loading evaluation targets."""
    output.mkdir(parents=True, exist_ok=True)
    destination = output / "poll_timing_plan.json"
    if destination.exists():
        raise FileExistsError("Keep the declared plan; use run or another output directory")
    campaign_path = campaign_dir / "campaign.json"
    comparison_path = comparison_dir / "polling_comparison.json"
    source_evidence_path = historical_polls.with_name("evidence.json")
    campaign, comparison, source_evidence = map(_read, [campaign_path, comparison_path, source_evidence_path])
    if campaign["status"] != "complete" or comparison["status"] != "complete":
        raise ValueError("Frozen structural and polling campaigns must be complete")
    validate_windows(campaign["plan"]["validation_windows"])
    params = campaign["plan"]["frozen_poll_parameters"]
    if params["trend_factor"] != 1.0 or params["max_trend_adjustment"] != .15:
        raise ValueError("Use the frozen unit trend and 15-point cap")
    structural = next(item for item in campaign["runs"] if item["name"] == "baseline_pca5")
    nominal = next(item for item in comparison["runs"] if item["name"] == "baseline_expanded_trend")
    original = next(item for item in comparison["runs"] if item["name"] == "baseline_original_trend")
    locations = {
        "dataset": (input_dir / "dataset.parquet", campaign["dataset_sha256"]),
        "base_manifest": (input_dir / "data_manifest.json", campaign["base_manifest_sha256"]),
        "campaign": (campaign_path, comparison["campaign_sha256"]),
        "structural_predictions": (campaign_dir / "baseline_pca5_predictions.parquet", structural["predictions_sha256"]),
        "nominal_predictions": (comparison_dir / "baseline_expanded_trend_predictions.parquet", nominal["predictions_sha256"]),
        "original_polls": (ROOT / "data/external/polls/srg_gfs_polls.csv", campaign["original_polls_sha256"]),
        "historical_polls": (historical_polls, source_evidence["validation"]["polls_csv_sha256"]),
    }
    if comparison["historical_polls_sha256"] != locations["historical_polls"][1]:
        raise ValueError("Source evidence and polling campaign disagree on historical CSV hash")
    for relative, expected in campaign["code"].items():
        _assert_hash(ROOT / relative, expected, relative)
    evidence = {}
    for label, (path, expected) in locations.items():
        evidence[label] = {"path": str(path.relative_to(ROOT)), "sha256": _assert_hash(path, expected, label)}
    for label, path in [("comparison", comparison_path), ("source_evidence", source_evidence_path),
                        ("sensitivity_code", Path(__file__))]:
        evidence[label] = {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}
    historical = pd.read_csv(historical_polls, dtype={"vote_key": "string", "survey_midpoint_is_approximate": "string"})
    flags = strict_flags(historical.survey_midpoint_is_approximate)
    # Validate bounds before declaring, without loading or scoring any outcome.
    for scenario in SCENARIOS:
        scenario_polls(historical, scenario["wave1"], scenario["wave2"])
    plan = {
        "declared_at_utc": datetime.now(timezone.utc).isoformat(),
        "declared_before_new_sensitivity_scores": True,
        "version": "municipal-v3-poll-timing-20261123",
        "scenarios": SCENARIOS,
        "mutation_policy": "Only survey_midpoint on explicit approximate=True rows; shares, publication, fieldwork and all calibration parameters unchanged",
        "frozen_poll_parameters": params,
        "validation_windows": campaign["plan"]["validation_windows"],
        "training_start": "1990-01-01", "evaluation_end": "2022-12-31",
        "metric": "Equal-object mean of unweighted municipal absolute errors in percentage points",
        "expected_rows": nominal["metrics"]["rows"], "expected_objects": nominal["metrics"]["objects"],
        "nominal_macro_object_mae_pp": nominal["metrics"]["macro_object_mae_pp"],
        "original_poll_macro_object_mae_pp": original["metrics"]["macro_object_mae_pp"],
        "approximate_poll_rows": int(flags.sum()),
        "approximate_objects": int(historical.loc[flags, "vote_key"].nunique()),
        "prediction_change_tolerance": 1e-12,
        "limitations": LIMITATION,
        "input_evidence": evidence,
        "frozen_campaign_code": campaign["code"],
        "no_tuning_or_model_selection": True,
        "comparison_targets_loaded": False,
    }
    write_json(destination, plan)
    print(f"Declared {len(SCENARIOS)} scenarios before evaluation: {destination}", flush=True)


def evaluate(data, combined_polls, fixed_model, windows, params):
    expanded, audit = add_poll_features(data, combined_polls)
    tables = []
    for window in windows:
        train = expanded[expanded.vote_date.lt(window["start"])]
        evaluation = expanded[expanded.vote_date.between(window["start"], window["end"])].copy()
        if train.vote_date.max() >= evaluation.vote_date.min():
            raise ValueError("Training/evaluation date overlap")
        anchored = PollAnchoredRegressor(fixed_model, **params).fit(train)
        prediction = anchored.predict(evaluation.drop(columns="yes_share"))
        table = evaluation[["municipality_id", "vote_id", "vote_date", "yes_share"]].copy()
        table["prediction"] = prediction
        table["window"] = window["name"]
        tables.append(table)
    return pd.concat(tables, ignore_index=True), audit


def run(output):
    plan_path = output / "poll_timing_plan.json"
    plan = _read(plan_path)
    if (output / "poll_timing_results.json").exists():
        raise FileExistsError("Preserve completed sensitivity results")
    if plan["scenarios"] != SCENARIOS:
        raise ValueError("Scenario definitions differ from the declared four-way endpoint comparison")
    validate_windows(plan["validation_windows"])
    paths = {}
    for label, entry in plan["input_evidence"].items():
        paths[label] = ROOT / entry["path"]
        _assert_hash(paths[label], entry["sha256"], label)
    for relative, expected in plan["frozen_campaign_code"].items():
        _assert_hash(ROOT / relative, expected, relative)
    historical = pd.read_csv(paths["historical_polls"], dtype={"vote_key": "string", "survey_midpoint_is_approximate": "string"})
    base = pd.read_csv(paths["original_polls"], dtype={"vote_key": "string"})
    base = base[pd.to_datetime(base.vote_date).lt("2023-01-01")].copy()
    detailed = ["yes_certain", "yes_lean", "no_certain", "no_lean"]
    base = base.drop(columns=detailed, errors="ignore")
    historical = historical.drop(columns=detailed, errors="ignore")
    required = ["municipality_id", "vote_id", "vote_key", "vote_date", "yes_share",
                "statpop_pop_total", "statpop_share_foreign", "statpop_share_0_19"]
    data = pd.read_parquet(paths["dataset"], columns=required, filters=[
        ("vote_date", ">=", pd.Timestamp("1990-01-01")),
        ("vote_date", "<", pd.Timestamp("2023-01-01")),
    ])
    if data.vote_date.ge("2023-01-01").any() or data.vote_date.lt("1990-01-01").any():
        raise ValueError("Out-of-scope target rows loaded")
    keys = ["municipality_id", "vote_id"]
    cached_columns = [*keys, "vote_date", "prediction"]
    structural = pd.read_parquet(paths["structural_predictions"], columns=cached_columns)
    nominal = pd.read_parquet(paths["nominal_predictions"], columns=cached_columns)
    for table in [data, structural, nominal]:
        for key in keys:
            table[key] = table[key].astype("string")
        if table.duplicated(keys).any() or table.vote_date.ge("2023-01-01").any():
            raise ValueError("Duplicate or out-of-scope cached/data rows")
    fixed = CachedPredictionModel(structural)
    nominal_values = nominal.set_index(keys).prediction
    records, object_tables, selected_midpoints = [], [], []
    all_scenarios = [{"name": "nominal", "wave1": None, "wave2": None}, *plan["scenarios"]]
    for scenario in all_scenarios:
        varied = historical if scenario["name"] == "nominal" else scenario_polls(
            historical, scenario["wave1"], scenario["wave2"]
        )
        combined = pd.concat([base, varied], ignore_index=True)
        if combined.duplicated(["vote_key", "wave"]).any():
            raise ValueError("Poll collections overlap")
        result, source_audit = evaluate(data, combined, fixed, plan["validation_windows"], plan["frozen_poll_parameters"])
        score, objects, _ = metrics(result)
        if score["rows"] != plan["expected_rows"] or score["objects"] != plan["expected_objects"]:
            raise ValueError("Sensitivity changed the evaluation population")
        index = pd.MultiIndex.from_frame(result[keys])
        reference = nominal_values.reindex(index)
        if reference.isna().any() or len(reference) != len(nominal_values):
            raise ValueError("Sensitivity predictions do not match the nominal evaluation keys")
        delta = result.prediction.to_numpy() - reference.to_numpy()
        changed = np.abs(delta) > plan["prediction_change_tolerance"]
        if scenario["name"] == "nominal" and (
            changed.any() or not np.isclose(
                score["macro_object_mae_pp"], plan["nominal_macro_object_mae_pp"], rtol=0, atol=1e-10
            )
        ):
            raise ValueError("Nominal endpoint pipeline does not reproduce the frozen polling comparison")
        change_table = result[["vote_id"]].assign(changed=changed, prediction_delta_pp=delta * 100)
        changes = change_table.groupby("vote_id", as_index=False).agg(
            changed_rows=("changed", "sum"), mean_prediction_delta_pp=("prediction_delta_pp", "mean")
        )
        objects = objects.merge(changes, on="vote_id", validate="one_to_one")
        objects["scenario"] = scenario["name"]
        object_tables.append(objects)
        selected_midpoints.append(varied[["record_id", "vote_key", "wave", "survey_midpoint", "survey_midpoint_is_approximate"]].assign(scenario=scenario["name"]))
        record = {
            **scenario, "metrics": score,
            "mae_delta_vs_nominal_pp": score["macro_object_mae_pp"] - plan["nominal_macro_object_mae_pp"],
            "mae_delta_vs_original_poll_trend_pp": score["macro_object_mae_pp"] - plan["original_poll_macro_object_mae_pp"],
            "changed_prediction_rows": int(changed.sum()),
            "changed_objects": int(result.loc[changed, "vote_id"].nunique()),
            "max_absolute_prediction_change_pp": float(np.max(np.abs(delta)) * 100),
            "source_poll_objects": source_audit["poll_objects"],
        }
        records.append(record)
        print(f"{scenario['name']}: {score['macro_object_mae_pp']:.10f} pp; changed rows {changed.sum()}", flush=True)
    pd.concat(object_tables, ignore_index=True).to_csv(output / "poll_timing_by_object.csv", index=False)
    pd.concat(selected_midpoints, ignore_index=True).to_csv(output / "poll_timing_selected_midpoints.csv", index=False)
    pd.DataFrame([{**{k: v for k, v in item.items() if k != "metrics"}, **item["metrics"]} for item in records]).to_csv(
        output / "poll_timing_scenarios.csv", index=False
    )
    endpoint_values = [item["metrics"]["macro_object_mae_pp"] for item in records if item["name"] != "nominal"]
    write_json(output / "poll_timing_results.json", {
        "status": "complete", "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "plan_sha256": sha(plan_path), "input_hashes_verified": True,
        "nominal_reproduced": True, "scenarios": records,
        "four_scenario_mae_range_pp": [min(endpoint_values), max(endpoint_values)],
        "original_poll_trend_mae_pp": plan["original_poll_macro_object_mae_pp"],
        "all_four_scenarios_improve_original_poll_trend": max(endpoint_values) < plan["original_poll_macro_object_mae_pp"],
        "comparison_targets_loaded": False, "structural_models_retrained": False,
        "calibration_parameters_changed": False, "strict_forecast_ready": False,
        "evaluation_end": "2022-12-31", "limitations": LIMITATION,
        "output_hashes": {name: sha(output / name) for name in [
            "poll_timing_by_object.csv", "poll_timing_selected_midpoints.csv", "poll_timing_scenarios.csv"
        ]},
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["declare", "run"])
    parser.add_argument("--input", type=Path, default=ROOT / "reports/generated/municipal_v3_base")
    parser.add_argument("--campaign", type=Path, default=ROOT / "reports/generated/municipal_v3_experiments_final")
    parser.add_argument("--comparison", type=Path, default=ROOT / "reports/generated/municipal_v3_polls_final")
    parser.add_argument("--historical-polls", type=Path, default=ROOT / "data/external/polls_historical_v3/polls.csv")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.command == "declare":
        declare(args.input, args.campaign, args.comparison, args.historical_polls, args.output)
    else:
        run(args.output)


if __name__ == "__main__":
    main()

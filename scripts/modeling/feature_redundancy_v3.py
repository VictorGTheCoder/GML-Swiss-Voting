"""Describe training-only feature redundancy at each feature's observation unit.

This audit never drops a model feature. Object attributes are assessed once per
object, municipal covariates once per source snapshot, and histories once per
municipality/date. Local interactions remain a dependent municipality/object
panel: their correlations are descriptive, with no independence or significance
claim. Only allowlisted predictors are read from the prepared Parquet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.common.config import ROOT
from scripts.modeling.municipal_v2 import FORBIDDEN, feature_columns

DEFAULT_CUTOFFS = ("2016-01-01", "2019-01-01", "2021-01-01")
FEATURE_FIELDS = (
    "cutoff", "scope", "feature", "type", "units", "observed", "missing",
    "missing_fraction", "unique_observed", "state",
)
PAIR_FIELDS = (
    "cutoff", "scope", "feature_a", "feature_b", "pair_kind", "units",
    "complete_pairs", "minimum_support", "sufficient_support", "pearson",
    "spearman", "same_missing_mask", "relation", "slope", "intercept",
    "maximum_residual", "affine_tolerance", "hard_redundancy_candidate",
)


def _deduplicate_units(frame: pd.DataFrame, keys: list[str], columns: list[str]) -> pd.DataFrame:
    """Reject conflicting values, rather than silently keeping the first copy."""
    selected = frame[list(dict.fromkeys(keys + columns))].drop_duplicates()
    if selected.duplicated(keys).any():
        raise ValueError(f"Predictors disagree within the declared unit {keys}")
    return selected.reset_index(drop=True)


def feature_scopes(frame: pd.DataFrame, manifest: dict) -> dict:
    """Use explicit feature contracts, never incidental within-object constancy."""
    numeric, categorical = feature_columns({"blocks": "direction"}, manifest)
    object_numeric = list(manifest["political"]["object_numeric_features"])
    object_numeric += list(manifest["direction"]["numeric_features"])
    object_categorical = [c for c in categorical if c.startswith("object_")]
    object_categorical += list(manifest["political"]["object_categorical_features"])
    local_numeric = [c for c in numeric if c.startswith(("statpop_", "party_share_")) or c == "log_population"]
    local_categorical = [c for c in categorical if c in ("canton", "urban_rural", "language_region")]
    historical_numeric = [c for c in numeric if c.startswith("history_")]
    interaction_numeric = [c for c in numeric if c.startswith("political_local_")]
    definitions = {
        "objects": {
            "keys": ["vote_id"], "numeric": object_numeric, "categorical": object_categorical,
            "interpretation": "One observation per training object; objects on the same date can still be dependent.",
        },
        "municipal_snapshots": {
            "keys": ["municipality_id", "statpop_year", "election_year"],
            "numeric": local_numeric, "categorical": local_categorical,
            "interpretation": "One municipality/source-year combination; repeated communes across snapshots remain dependent.",
        },
        "municipal_history": {
            "keys": ["municipality_id", "vote_date"], "numeric": historical_numeric, "categorical": [],
            "interpretation": "One municipality/voting-date combination, excluding duplicate same-day objects; no independence claim.",
        },
        "local_interactions": {
            "keys": ["municipality_id", "vote_id"], "numeric": interaction_numeric, "categorical": [],
            "interpretation": "Dependent municipality/object panel; descriptive correlation, not independent sample size or evidence of significance.",
        },
    }
    result = {}
    for name, definition in definitions.items():
        columns = list(dict.fromkeys(definition["numeric"] + definition["categorical"]))
        if set(columns) & FORBIDDEN:
            raise ValueError("Outcome or identifier attempted to enter the feature audit")
        result[name] = {
            **definition, "data": _deduplicate_units(frame, definition["keys"], columns),
        }
    return result


def audit_scope(
    frame: pd.DataFrame,
    numeric: list[str],
    categorical: list[str],
    *,
    minimum_support: int = 20,
    correlation_threshold: float = 0.95,
    affine_tolerance: float = 1e-10,
) -> tuple[list[dict], list[dict]]:
    """Find descriptive correlations and exact/affine redundancy candidates.

    Pairwise-complete correlation alone never proves that one column can replace
    another: both columns must have the identical missingness mask. Binary
    predictors are valid; fewer than ``minimum_support`` complete observations
    are insufficient. Constant/all-missing columns are reported separately.
    """
    if minimum_support < 3 or not 0 < correlation_threshold <= 1:
        raise ValueError("Require support >=3 and a correlation threshold in (0, 1]")
    if not np.isfinite(affine_tolerance) or affine_tolerance <= 0:
        raise ValueError("Affine tolerance must be positive and finite")
    columns = numeric + categorical
    if len(set(columns)) != len(columns) or not frame.columns.is_unique:
        raise ValueError("Predictor names must be unique")
    if set(columns) & FORBIDDEN:
        raise ValueError("Outcome or identifier attempted to enter the feature audit")
    values = frame[numeric].apply(pd.to_numeric, errors="raise").astype(float)
    if np.isinf(values.to_numpy()).any():
        raise ValueError("Infinite predictor values are invalid")
    inventory = []
    for column in columns:
        series = values[column] if column in numeric else frame[column]
        observed = int(series.notna().sum())
        distinct = int(series.nunique(dropna=True))
        inventory.append({
            "feature": column, "type": "numeric" if column in numeric else "categorical",
            "units": len(frame), "observed": observed, "missing": len(frame) - observed,
            "missing_fraction": (len(frame) - observed) / len(frame) if len(frame) else None,
            "unique_observed": distinct,
            "state": "all_missing" if not distinct else "constant_when_observed" if distinct == 1 else "variable",
        })
    variable = [entry["feature"] for entry in inventory if entry["state"] == "variable" and entry["type"] == "numeric"]
    pearson = values[variable].corr(method="pearson", min_periods=3)
    spearman = values[variable].corr(method="spearman", min_periods=3)
    pairs = []
    for a, b in combinations(variable, 2):
        p, s = float(pearson.loc[a, b]), float(spearman.loc[a, b])
        if not ((np.isfinite(p) and abs(p) >= correlation_threshold) or
                (np.isfinite(s) and abs(s) >= correlation_threshold)):
            continue
        complete = values[a].notna() & values[b].notna()
        x, y = values.loc[complete, a].to_numpy(), values.loc[complete, b].to_numpy()
        sufficient = len(x) >= minimum_support
        same_mask = bool(values[a].isna().equals(values[b].isna()))
        relation, slope, intercept, residual = "correlated_only", None, None, None
        if len(x) >= 3 and same_mask:
            if np.array_equal(x, y):
                relation, slope, intercept, residual = "exact_duplicate", 1.0, 0.0, 0.0
            elif np.array_equal(x, -y):
                relation, slope, intercept, residual = "exact_opposite", -1.0, 0.0, 0.0
            elif np.isfinite(p) and abs(p) >= 1 - 1e-12:
                xc = x - x.mean()
                slope = float(np.dot(xc, y - y.mean()) / np.dot(xc, xc))
                intercept = float(y.mean() - slope * x.mean())
                residual = float(np.max(np.abs(y - (slope * x + intercept))))
                if residual <= affine_tolerance * max(1.0, float(np.max(np.abs(y)))):
                    relation = "affine_within_tolerance"
        pairs.append({
            "feature_a": a, "feature_b": b, "pair_kind": "numeric", "units": len(frame),
            "complete_pairs": len(x), "minimum_support": minimum_support, "sufficient_support": sufficient,
            "pearson": p if np.isfinite(p) else None, "spearman": s if np.isfinite(s) else None,
            "same_missing_mask": same_mask, "relation": relation, "slope": slope, "intercept": intercept,
            "maximum_residual": residual, "affine_tolerance": affine_tolerance,
            "hard_redundancy_candidate": sufficient and same_mask and relation != "correlated_only",
        })
    variable_categories = [entry["feature"] for entry in inventory if entry["state"] == "variable" and entry["type"] == "categorical"]
    for a, b in combinations(variable_categories, 2):
        x, y = frame[a], frame[b]
        if not x.isna().equals(y.isna()):
            continue
        observed = x.notna()
        if not x[observed].astype(str).equals(y[observed].astype(str)):
            continue
        count = int(observed.sum())
        pairs.append({
            "feature_a": a, "feature_b": b, "pair_kind": "categorical", "units": len(frame),
            "complete_pairs": count, "minimum_support": minimum_support,
            "sufficient_support": count >= minimum_support, "pearson": None, "spearman": None,
            "same_missing_mask": True, "relation": "exact_duplicate", "slope": None,
            "intercept": None, "maximum_residual": None, "affine_tolerance": None,
            "hard_redundancy_candidate": count >= minimum_support,
        })
    return inventory, pairs


def run_audit(input_directory: Path, output_directory: Path, *, cutoffs=DEFAULT_CUTOFFS,
              train_start="1990-01-01", minimum_support=20, correlation_threshold=0.95) -> dict:
    manifest_path = input_directory / "data_manifest.json"
    dataset_path = input_directory / "dataset.parquet"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    numeric, categorical = feature_columns({"blocks": "direction"}, manifest)
    columns = list(dict.fromkeys(
        ["municipality_id", "vote_id", "vote_date", "statpop_year", "election_year"] + numeric + categorical))
    cutoff_dates = [pd.Timestamp(c) for c in cutoffs]
    start = pd.Timestamp(train_start)
    if not cutoff_dates or any(c <= start for c in cutoff_dates):
        raise ValueError("All training cutoffs must follow the training start")
    if max(cutoff_dates) > pd.Timestamp("2023-01-01"):
        raise ValueError("Do not use the retrospective comparison period in a development feature audit")
    # Outcomes are not loaded; Parquet filters exclude later development periods.
    table = pd.read_parquet(dataset_path, columns=columns,
                            filters=[("vote_date", ">=", start), ("vote_date", "<", max(cutoff_dates))])
    inventory, pairs, scopes = [], [], []
    for cutoff in sorted(set(cutoff_dates)):
        train = table.loc[table.vote_date.lt(cutoff)]
        if train.empty:
            raise ValueError(f"Empty training window before {cutoff.date()}")
        for name, definition in feature_scopes(train, manifest).items():
            frame = definition["data"]
            feature_rows, pair_rows = audit_scope(
                frame, definition["numeric"], definition["categorical"],
                minimum_support=minimum_support, correlation_threshold=correlation_threshold,
            )
            context = {"cutoff": str(cutoff.date()), "scope": name}
            inventory.extend([{**context, **row} for row in feature_rows])
            pairs.extend([{**context, **row} for row in pair_rows])
            scopes.append({
                **context, "training_rows": len(train), "training_objects": int(train.vote_id.nunique()),
                "training_dates": int(train.vote_date.nunique()), "units": len(frame),
                "keys": definition["keys"], "features": len(feature_rows),
                "all_missing": sum(row["state"] == "all_missing" for row in feature_rows),
                "constant_when_observed": sum(row["state"] == "constant_when_observed" for row in feature_rows),
                "high_correlation_pairs": len(pair_rows),
                "hard_redundancy_pairs": sum(row["hard_redundancy_candidate"] for row in pair_rows),
                "interpretation": definition["interpretation"],
            })
            print(json.dumps({**context, "units": len(frame), "pairs": len(pair_rows)}), flush=True)
    output_directory.mkdir(parents=True, exist_ok=True)
    paths = [output_directory / ("correlation_" + suffix) for suffix in
             ("features.csv", "pairs.csv", "scopes.csv", "audit.json")]
    if any(path.exists() for path in paths):
        raise FileExistsError("Preserve an existing audit; choose a new output directory")
    summary = {
        "schema_version": 1, "purpose": "Descriptive redundancy audit; no feature or model changed",
        "training_start": str(start.date()), "training_cutoffs_exclusive": [str(c.date()) for c in sorted(set(cutoff_dates))],
        "minimum_complete_support": minimum_support, "correlation_threshold": correlation_threshold,
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "input_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "target_columns_loaded": [], "feature_selection_performed": False,
        "scopes": scopes,
        "limitations": [
            "Pairwise correlations do not detect all multivariate or nonlinear redundancy.",
            "A high absolute correlation is not by itself a reason to remove a feature.",
            "Hard redundancy candidates have matching missingness and adequate support; they still need fold-local validation.",
            "Constant-when-observed is not equivalent to uninformative: its missingness may carry a signal.",
            "Historical source availability and fixed 2026 geography retain the V2 retrospective limitations.",
            "Correlations across repeated communes and same-day objects are descriptive; no p-values are reported.",
            "Raw features are audited before one-hot encoding; complementary dummy columns are not counted as scientific redundancy.",
        ],
    }
    pd.DataFrame(inventory, columns=FEATURE_FIELDS).to_csv(paths[0], index=False)
    pd.DataFrame(pairs, columns=PAIR_FIELDS).to_csv(paths[1], index=False)
    pd.DataFrame(scopes).to_csv(paths[2], index=False)
    paths[3].write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "reports/generated/municipal_v3_base")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/datasets/municipal_v3_20261123")
    parser.add_argument("--cutoffs", nargs="+", default=list(DEFAULT_CUTOFFS))
    parser.add_argument("--train-start", default="1990-01-01")
    parser.add_argument("--minimum-support", type=int, default=20)
    parser.add_argument("--correlation-threshold", type=float, default=0.95)
    args = parser.parse_args(argv)
    run_audit(args.input, args.output, cutoffs=args.cutoffs, train_start=args.train_start,
              minimum_support=args.minimum_support, correlation_threshold=args.correlation_threshold)


if __name__ == "__main__":
    main()

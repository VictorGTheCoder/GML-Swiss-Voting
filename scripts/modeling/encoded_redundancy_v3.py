"""Audit the actual V2 object design after training-only preprocessing.

Read only object attributes, never targets. Use the exact V2 imputation,
missingness indicators, scaling and one-hot encoder on one row per training
object. Report constant and pairwise redundant columns without dropping any.
Empirical equality on past objects is not a guarantee for unseen categories.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as arrow_dataset
import sklearn
from threadpoolctl import threadpool_limits

from scripts.common.config import ROOT
from scripts.modeling.feature_redundancy_v3 import (
    DEFAULT_CUTOFFS,
    FEATURE_FIELDS,
    PAIR_FIELDS,
    _deduplicate_units,
    audit_scope,
)
from scripts.modeling.object_profile_v2 import ObjectProfileRegressor


def file_hash(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def object_features(manifest):
    """Exactly the object feature lists of the frozen political-profile variant."""
    numeric = list(manifest["political"]["object_numeric_features"])
    categorical = ["object_legal_form", "object_domain_1", "object_domain_2", "object_domain_3"]
    categorical += list(manifest["political"]["object_categorical_features"])
    return numeric, categorical


def read_object_units(path, numeric, categorical, *, start, end):
    """Stream municipal rows and reject conflicts while retaining one object row."""
    columns = ["vote_id", "vote_date", *numeric, *categorical]
    dataset = arrow_dataset.dataset(path, format="parquet")
    condition = ((arrow_dataset.field("vote_date") >= pd.Timestamp(start).to_pydatetime()) &
                 (arrow_dataset.field("vote_date") < pd.Timestamp(end).to_pydatetime()))
    pieces = []
    for batch in dataset.scanner(columns=columns, filter=condition, batch_size=16384).to_batches():
        frame = batch.to_pandas()
        if not frame.empty:
            pieces.append(_deduplicate_units(frame, ["vote_id"], columns[1:]))
    if not pieces:
        raise ValueError("No objects in the declared training interval")
    result = _deduplicate_units(pd.concat(pieces, ignore_index=True), ["vote_id"], columns[1:])
    # The V2 object-table helper requires this row key. It is not a predictor,
    # no municipal profile is fitted, and the label deliberately conveys no place.
    result["municipality_id"] = "__object_audit_only__"
    return result.sort_values(["vote_date", "vote_id"]).reset_index(drop=True)


def fit_object_design(train, numeric, categorical):
    """Fit only V2's feature transformer; never invoke model.fit or read y."""
    contract = ObjectProfileRegressor(numeric, categorical)
    contract._validate_feature_lists()
    objects, _, _ = contract._object_table(train)
    preprocessor = contract._make_preprocessor()
    design = preprocessor.fit_transform(objects)
    names = preprocessor.get_feature_names_out()
    return pd.DataFrame(design, index=objects.index, columns=names), preprocessor


def run_audit(input_directory, output_directory, *, cutoffs=DEFAULT_CUTOFFS,
              train_start="1990-01-01", minimum_support=20, correlation_threshold=.95):
    input_directory, output_directory = Path(input_directory), Path(output_directory)
    manifest_path, dataset_path = input_directory / "data_manifest.json", input_directory / "dataset.parquet"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dataset_hash = file_hash(dataset_path)
    if dataset_hash != manifest["dataset_sha256"]:
        raise ValueError("Base dataset hash mismatch")
    numeric, categorical = object_features(manifest)
    start = pd.Timestamp(train_start)
    ends = sorted({pd.Timestamp(c) for c in cutoffs})
    if not ends or any(c <= start or c > pd.Timestamp("2023-01-01") for c in ends):
        raise ValueError("Training cutoffs must follow the start and exclude comparison-period objects")
    destinations = {name: output_directory / ("correlation_encoded_" + name + suffix)
                    for name, suffix in (("features", ".csv"), ("pairs", ".csv"), ("scopes", ".csv"), ("audit", ".json"))}
    if any(path.exists() for path in destinations.values()):
        raise FileExistsError("Preserve the existing encoded audit; choose a new output directory")
    units = read_object_units(dataset_path, numeric, categorical, start=start, end=ends[-1])
    features, pairs, scopes = [], [], []
    for cutoff in ends:
        train = units.loc[units.vote_date.lt(cutoff)]
        if train.empty:
            raise ValueError("Empty training fold")
        design, _ = fit_object_design(train, numeric, categorical)
        inventory, correlations = audit_scope(
            design, list(design), [], minimum_support=minimum_support,
            correlation_threshold=correlation_threshold,
        )
        context = {"cutoff": str(cutoff.date()), "scope": "object_encoded"}
        frequencies = {c: int(design[c].value_counts().min()) for c in design}
        features.extend([{**context, **row, "minimum_observed_value_frequency": frequencies[row["feature"]]}
                         for row in inventory])
        pairs.extend([{
            **context, **row,
            "minimum_observed_value_frequency_a": frequencies[row["feature_a"]],
            "minimum_observed_value_frequency_b": frequencies[row["feature_b"]],
            "future_equivalence_proven": False,
        } for row in correlations])
        with threadpool_limits(limits=1):
            matrix = design.to_numpy(float)
            rank = int(np.linalg.matrix_rank(matrix))
            centered_rank = int(np.linalg.matrix_rank(matrix - matrix.mean(axis=0)))
        scopes.append({
            **context, "training_objects": len(design), "training_dates": int(train.vote_date.nunique()),
            "raw_numeric_features": len(numeric), "raw_categorical_features": len(categorical),
            "encoded_columns": len(design.columns), "matrix_rank": rank, "centered_matrix_rank": centered_rank,
            "constant_columns": sum(row["state"] != "variable" for row in inventory),
            "high_correlation_pairs": len(correlations),
            "hard_redundancy_candidate_pairs": sum(row["hard_redundancy_candidate"] for row in correlations),
            "exact_duplicate_pairs": sum(row["relation"] == "exact_duplicate" for row in correlations),
            "exact_opposite_pairs": sum(row["relation"] == "exact_opposite" for row in correlations),
            "affine_candidate_pairs": sum(row["relation"] == "affine_within_tolerance" for row in correlations),
        })
        print(json.dumps(scopes[-1]), flush=True)
    report = {
        "schema_version": 1, "model_feature_variant": "V2 political object profile, no lexical direction extension",
        "training_start": str(start.date()), "training_cutoffs_exclusive": [str(c.date()) for c in ends],
        "dataset_sha256": dataset_hash, "input_manifest_sha256": file_hash(manifest_path),
        "code_sha256": file_hash(__file__),
        "v2_preprocessor_code_sha256": file_hash(ROOT / "scripts/modeling/object_profile_v2.py"),
        "sklearn_version": sklearn.__version__,
        "numeric_features": numeric, "categorical_features": categorical,
        "target_columns_loaded": [], "regressors_fitted": False, "columns_removed": [],
        "preprocessor_fit_scope": "one row per training object, exclusive date cutoff",
        "minimum_complete_support": minimum_support, "correlation_threshold": correlation_threshold,
        "scopes": scopes,
        "limitations": [
            "These equivalences describe the fitted design on training objects, not all possible future inputs.",
            "Two one-hot columns can coincide merely because rare source categories coincided historically; inspect value frequencies.",
            "Complementary one-hot columns can stop being complementary when a future unseen category is encoded as all zeros.",
            "A numeric sign and categorical indicators may encode the same information after imputation; retain missingness and unknown-category semantics when testing removal.",
            "Matrix rank also detects multivariate linear dependencies, but is not a feature-selection rule for nonlinear trees.",
            "No prediction, score, preprocessing rule or frozen candidate has been changed by this audit.",
        ],
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(features, columns=[*FEATURE_FIELDS, "minimum_observed_value_frequency"]).to_csv(destinations["features"], index=False)
    pd.DataFrame(pairs, columns=[*PAIR_FIELDS, "minimum_observed_value_frequency_a",
                                "minimum_observed_value_frequency_b", "future_equivalence_proven"]).to_csv(destinations["pairs"], index=False)
    pd.DataFrame(scopes).to_csv(destinations["scopes"], index=False)
    destinations["audit"].write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "reports/generated/municipal_v3_base")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/datasets/municipal_v3_20261123")
    parser.add_argument("--cutoffs", nargs="+", default=list(DEFAULT_CUTOFFS))
    args = parser.parse_args(argv)
    run_audit(args.input, args.output, cutoffs=args.cutoffs)


if __name__ == "__main__":
    main()

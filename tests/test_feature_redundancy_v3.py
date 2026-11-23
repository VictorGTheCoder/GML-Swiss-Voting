"""Ensure redundancy reports respect missingness, units and training boundaries."""

import numpy as np
import pandas as pd
import pytest

from scripts.modeling.feature_redundancy_v3 import _deduplicate_units, audit_scope


def test_exact_positive_negative_and_affine_relations_are_identified():
    x = np.arange(30, dtype=float)
    frame = pd.DataFrame({"x": x, "copy": x, "opposite": -x, "affine": 2 * x + 3})
    _, pairs = audit_scope(frame, list(frame), [])
    by_pair = {(row["feature_a"], row["feature_b"]): row for row in pairs}
    assert by_pair["x", "copy"]["relation"] == "exact_duplicate"
    assert by_pair["x", "opposite"]["relation"] == "exact_opposite"
    assert by_pair["x", "affine"]["relation"] == "affine_within_tolerance"
    assert by_pair["x", "affine"]["slope"] == pytest.approx(2)
    assert by_pair["x", "affine"]["intercept"] == pytest.approx(3)
    assert all(row["hard_redundancy_candidate"] for row in pairs)


def test_perfect_overlap_correlation_with_different_missingness_is_not_redundancy():
    x = np.arange(40, dtype=float)
    frame = pd.DataFrame({"x": x, "y": x})
    frame.loc[0, "x"] = np.nan
    frame.loc[1, "y"] = np.nan
    _, pairs = audit_scope(frame, list(frame), [])
    assert len(pairs) == 1
    assert pairs[0]["pearson"] == pytest.approx(1)
    assert pairs[0]["complete_pairs"] == 38
    assert not pairs[0]["same_missing_mask"]
    assert not pairs[0]["hard_redundancy_candidate"]


def test_rare_identical_values_do_not_meet_minimum_support():
    frame = pd.DataFrame({"x": [1., 2., 3., np.nan], "y": [1., 2., 3., np.nan]})
    _, pairs = audit_scope(frame, list(frame), [])
    assert pairs[0]["relation"] == "exact_duplicate"
    assert not pairs[0]["sufficient_support"]
    assert not pairs[0]["hard_redundancy_candidate"]


def test_binary_predictors_are_valid_when_observation_support_is_sufficient():
    x = np.tile([0., 1.], 20)
    frame = pd.DataFrame({"a": x, "b": 1 - x})
    _, pairs = audit_scope(frame, list(frame), [])
    assert pairs[0]["relation"] == "affine_within_tolerance"
    assert pairs[0]["hard_redundancy_candidate"]


def test_spearman_detects_monotonic_nonlinear_relationship_without_claiming_affinity():
    x = np.linspace(0, 1, 50)
    frame = pd.DataFrame({"x": x, "cubed": x ** 3})
    _, pairs = audit_scope(frame, list(frame), [])
    assert len(pairs) == 1
    assert pairs[0]["pearson"] < .95
    assert pairs[0]["spearman"] == pytest.approx(1)
    assert pairs[0]["relation"] == "correlated_only"
    assert not pairs[0]["hard_redundancy_candidate"]


def test_constants_all_missing_and_partial_missing_constant_are_distinct():
    frame = pd.DataFrame({"empty": [np.nan] * 30, "fixed": [1.] * 30,
                          "sparse_fixed": [2.] * 10 + [np.nan] * 20})
    inventory, pairs = audit_scope(frame, list(frame), [])
    assert not pairs
    rows = {row["feature"]: row for row in inventory}
    assert rows["empty"]["state"] == "all_missing"
    assert rows["fixed"]["state"] == "constant_when_observed"
    assert rows["sparse_fixed"]["missing"] == 20


def test_repeated_rows_do_not_change_unit_level_correlations_or_support():
    source = pd.DataFrame({"unit": np.arange(30), "x": np.arange(30), "y": -np.arange(30)})
    repeated = pd.concat([source] + [source.iloc[:10]] * 8, ignore_index=True)
    first = _deduplicate_units(source, ["unit"], ["x", "y"])
    second = _deduplicate_units(repeated, ["unit"], ["x", "y"])
    assert audit_scope(first, ["x", "y"], []) == audit_scope(second, ["x", "y"], [])


def test_conflicting_unit_values_are_rejected_instead_of_arbitrarily_deduplicated():
    frame = pd.DataFrame({"unit": [1, 1], "x": [1., 2.]})
    with pytest.raises(ValueError, match="disagree"):
        _deduplicate_units(frame, ["unit"], ["x"])


def test_outcome_and_infinite_features_are_rejected():
    with pytest.raises(ValueError, match="Outcome"):
        audit_scope(pd.DataFrame({"yes_share": [.1, .2]}), ["yes_share"], [])
    with pytest.raises(ValueError, match="Infinite"):
        audit_scope(pd.DataFrame({"x": [1., np.inf]}), ["x"], [])


def test_categorical_duplicates_require_identical_missingness():
    x = ["yes", "no"] * 15
    frame = pd.DataFrame({"x": x, "copy": x, "different_mask": x})
    frame.loc[0, "different_mask"] = None
    _, pairs = audit_scope(frame, [], list(frame))
    assert len(pairs) == 1
    assert pairs[0]["feature_a"] == "x"
    assert pairs[0]["feature_b"] == "copy"
    assert pairs[0]["hard_redundancy_candidate"]

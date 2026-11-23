"""Target-free reconstruction and fixed capacity sweep regression tests."""

import numpy as np
import pytest
from sklearn.decomposition import PCA

from scripts.modeling.audit_xgboost_capacity import (
    EXTENDED_GRID,
    EXTENDED_STEPS,
    GRID,
    STEPS,
    anchor_fast,
    diagnostics,
    reconstruct,
)
from scripts.modeling.object_profile_v2 import ObjectProfileRegressor


def test_frozen_baseline_and_effective_leaf_parameters():
    assert 300 in STEPS
    assert GRID["depth_6"] == {"max_depth": 6}
    pytest.importorskip("xgboost")
    model = ObjectProfileRegressor([], [], model="xgboost", min_samples_leaf=11)
    assert model._make_regressor().get_params().get("min_child_weight") in (None, 1)
    assert GRID["child_15"]["model_params"]["min_child_weight"] == 15


def test_macro_score_counts_objects_not_rows():
    y = np.array([0.2, 0.4, 0.5])
    p = np.array([0.4, 0.6, 0.5])
    score, mae = diagnostics(y, p, np.array([0, 0, 1]), 2)
    np.testing.assert_allclose(mae, [20, 0])
    assert abs(score["mae"] - 10) < 1e-10
    assert score["centered_mae"] < 1e-10


def test_anchor_reaches_target_and_preserves_unpolled_values():
    p = np.array([0.1, 0.3, 0.9, 0.55])
    weights = np.array([0.2, 0.3, 0.5])
    result = anchor_fast(p, [(np.array([0, 1, 2]), weights, 0.8)])
    assert abs(weights @ result[:3] - 0.8) < 1e-10
    assert result[-1] == p[-1]
    assert np.all((result >= 0) & (result <= 1))


def test_unknown_municipality_falls_back_to_object_level():
    pca = PCA(n_components=1).fit(np.array([[0.1, -0.1], [-0.1, 0.1], [0.0, 0.0]]))
    heads = np.array([[0.6, 0.3]])
    result = reconstruct(heads, pca, np.array([0, 0]), np.array([0, -1]))
    assert result[-1] == 0.6


def test_extended_capacity_is_effectively_larger():
    assert EXTENDED_STEPS[-1] == 2400
    assert EXTENDED_GRID["depth_16"]["max_depth"] == 16
    assert EXTENDED_GRID["depth_unlimited"]["model_params"]["max_depth"] == 0
    pytest.importorskip("xgboost")
    model = ObjectProfileRegressor([], [], model="xgboost", **EXTENDED_GRID["depth_unlimited"])
    assert model._make_regressor().get_params()["max_depth"] == 0

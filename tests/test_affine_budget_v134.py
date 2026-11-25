import numpy as np
import pytest
from scipy.optimize import linprog

from scripts.modeling.affine_budget_v134 import affine_diagnosis


def test_positive_affine_removes_amplitude_and_offset():
    result = affine_diagnosis([.1, .3, .5, .7], [.2, .3, .4, .5])
    assert result["affine_oracle_pp"] == pytest.approx(0, abs=1e-6)
    assert result["amplitude_oracle_gain_pp"] == pytest.approx(10)
    assert set(result) == {"mae_pp", "centered_mae_pp", "median_offset_oracle_pp",
                           "local_oracle_gain_pp", "affine_oracle_pp", "amplitude_oracle_gain_pp"}


def test_reversed_order_cannot_be_inverted():
    result = affine_diagnosis([.1, .3, .5, .7], [.7, .5, .3, .1])
    assert result["affine_oracle_pp"] == pytest.approx(20)


def test_constant_vectors():
    assert affine_diagnosis([.1, .3, .5], [.2, .2, .2])["affine_oracle_pp"] == pytest.approx(40/3)
    assert affine_diagnosis([.3, .3], [.2, .8])["affine_oracle_pp"] == 0


def test_matches_independent_linear_program():
    rng = np.random.default_rng(134)
    for _ in range(12):
        y, p = rng.uniform(0, 1, (2, 21))
        n = len(y)
        eye = np.eye(n)
        design = np.column_stack([np.ones(n), p])
        constraints = np.vstack([np.column_stack([design, -eye]),
                                 np.column_stack([-design, -eye])])
        fit = linprog(np.r_[0., 0., np.ones(n)/n], A_ub=constraints,
                      b_ub=np.r_[y, -y], bounds=[(None, None), (0, None)] + [(0, None)] * n,
                      method="highs")
        assert fit.success
        assert affine_diagnosis(y, p)["affine_oracle_pp"] == pytest.approx(100*fit.fun, abs=1e-6)


def test_invalid_values():
    with pytest.raises(ValueError):
        affine_diagnosis([.1], [np.nan])

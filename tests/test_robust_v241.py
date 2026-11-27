import numpy as np
import pytest

from scripts.modeling.object_profile_v2 import ObjectProfileRegressor
from scripts.modeling.robust_v241 import scaled_heads


def sample():
    x = np.arange(24, dtype=float).reshape(12, 2)
    y = np.column_stack([np.sin(x[:, 0]), np.full(12, 4.0)])
    proto = ObjectProfileRegressor([], [], model="xgboost", n_estimators=5,
                                   max_depth=2, n_jobs=1, random_state=42)
    return proto, x, y


@pytest.mark.parametrize("objective", ["reg:squarederror", "reg:pseudohubererror"])
def test_shape_constant_and_query_invariance(objective):
    proto, x, y = sample()
    q = np.array([[1., 2.], [20., 21.]])
    a = scaled_heads(proto, x, y, q, objective)
    b = scaled_heads(proto, x, y, np.vstack([q, [[100., -100.]]]), objective)
    assert a.shape == (2, 2)
    assert np.isfinite(a).all()
    np.testing.assert_allclose(a[:, 1], 4.0)
    np.testing.assert_allclose(a, b[:2], atol=1e-7)


def test_train_scale_equivariance():
    proto, x, y = sample()
    q = x[:3]
    a = scaled_heads(proto, x, y, q, "reg:pseudohubererror")
    b = scaled_heads(proto, x, 7 * y + 2, q, "reg:pseudohubererror")
    np.testing.assert_allclose(7 * a + 2, b, atol=1e-5)


def test_reject_nonfinite_and_unknown_objective():
    proto, x, y = sample()
    with pytest.raises(ValueError):
        scaled_heads(proto, x, y, x[:2], "unknown")
    y[0, 0] = np.nan
    with pytest.raises(ValueError):
        scaled_heads(proto, x, y, x[:2], "reg:squarederror")

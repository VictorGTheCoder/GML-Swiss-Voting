import numpy as np
import pytest

from scripts.modeling.object_profile_v2 import ObjectProfileRegressor
from scripts.modeling.shared_v271 import shared_heads


def sample():
    x = np.arange(48, dtype=float).reshape(24, 2)
    y = np.column_stack([np.sin(x[:, 0]), np.cos(x[:, 0]), np.full(24, 4.0)])
    proto = ObjectProfileRegressor([], [], model="xgboost", n_estimators=5,
                                   max_depth=2, n_jobs=1, random_state=42)
    return proto, x, y


def test_shared_shape_and_query_invariance():
    pytest.importorskip("xgboost")
    proto, x, y = sample()
    q = x[:4]
    a = shared_heads(proto, x, y, q)
    b = shared_heads(proto, x, y, np.vstack([q, [[100., -100.]]]))
    assert a.shape == (4, 3)
    assert np.isfinite(a).all()
    np.testing.assert_allclose(a[:, 2], 4.0)
    np.testing.assert_allclose(a, b[:4], atol=1e-7)


def test_shared_train_scale_equivariance():
    pytest.importorskip("xgboost")
    proto, x, y = sample()
    a = shared_heads(proto, x, y, x[:3])
    b = shared_heads(proto, x, 7 * y + 2, x[:3])
    np.testing.assert_allclose(7 * a + 2, b, atol=1e-5)


def test_constant_and_invalid_targets():
    proto, x, y = sample()
    np.testing.assert_allclose(shared_heads(proto, x, np.ones_like(y), x[:3]), 1.)
    y[0, 0] = np.nan
    with pytest.raises(ValueError):
        shared_heads(proto, x, y, x[:3],)

import numpy as np
import pandas as pd

from scripts.modeling.pooling_v104 import apply_correction, fit_correction, history_cells


def test_strict_prior_date_and_shrinkage():
    keys = [("de", "rural"), ("fr", "large")]
    history = []
    for i in range(9):
        day = pd.Timestamp("2017-01-01") + pd.Timedelta(days=i)
        history.extend(history_cells(str(i), day, keys, "x", True, False,
                                     np.array([.7, .3]), np.array([.5, .5])))
    target = pd.Timestamp("2018-01-01")
    a, n = fit_correction(history, target, keys, "x", True, False, "crossed", 2.)
    history.extend(history_cells("target", target, keys, "x", True, False,
                                 np.array([0., 1.]), np.array([.5, .5])))
    b, n2 = fit_correction(history, target, keys, "x", True, False, "crossed", 2.)
    assert n == n2 == 9
    np.testing.assert_allclose(a, b)
    assert 0 < a[0] < .2 and -.2 < a[1] < 0


def test_cold_start():
    a, n = fit_correction([], pd.Timestamp("2018-01-01"), [("de", "rural")],
                          "x", False, False, "domain", 4.)
    assert n == 0
    np.testing.assert_array_equal(a, [0.])


def test_national_coherence_and_bounds():
    p = np.array([.1, .8])
    w = np.array([10., 2.])
    q = apply_correction(p, w, np.array([-.4, .5]))
    assert np.all((q >= 0) & (q <= 1))
    assert abs(np.average(p, weights=w) - np.average(q, weights=w)) < 1e-8


def test_object_weights_and_centering():
    r = history_cells("v", pd.Timestamp("2018-01-01"),
                      [("de", "rural"), ("de", "rural"), ("fr", "large")],
                      "x", False, False, np.array([.7, .8, .3]), np.array([.5, .5, .5]))
    assert np.isclose(sum(x["weight"] for x in r), 1.)
    assert np.isclose(sum(x["weight"] * x["residual"] for x in r), 0.)

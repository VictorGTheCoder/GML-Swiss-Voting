"""Tests for reduced hierarchical reconciliation."""
import numpy as np
import pandas as pd
import pytest

from scripts.modeling.reconcile_v106 import distribute, error_covariance, reconcile


def test_coherent_inputs_unchanged():
    w = np.array([.3, .7])
    b = np.array([.4, .6])
    result = reconcile(w @ b, b, b, w, np.eye(5))
    np.testing.assert_allclose(result, b)


def test_fixed_national_constraint_and_bounds():
    w = np.array([1., 3.])
    q = reconcile(.4, [.1, .5], [0., 1.], w, np.eye(5), True)
    assert np.average(q, weights=w) == pytest.approx(.4)
    assert np.all((q >= 0) & (q <= 1))


def test_covariance_ignores_current_and_future():
    day = pd.Timestamp("2020-01-02")
    past = [(pd.Timestamp("2020-01-01"), np.arange(5) * .01 * i) for i in range(8)]
    a, n = error_covariance(past, day, 2, .25)
    b, m = error_covariance(past + [(day, np.ones(5)*1000),
                                   (day + pd.Timedelta(days=1), np.ones(5)*1000)], day, 2, .25)
    assert n == m == 8
    np.testing.assert_array_equal(a, b)
    assert np.linalg.eigvalsh(a).min() > 0


def test_distribute_preserves_canton_targets():
    p = np.array([.1, .3, .6, .9])
    w = np.array([1., 2., 3., 4.])
    c = np.array(["AA", "AA", "BB", "BB"])
    q = distribute(p, w, c, ["AA", "BB"], [.05, .95])
    assert np.average(q[:2], weights=w[:2]) == pytest.approx(.05)
    assert np.average(q[2:], weights=w[2:]) == pytest.approx(.95)

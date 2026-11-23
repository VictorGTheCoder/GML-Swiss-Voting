"""Tests for the inductive factorization's train-only geometry."""
import numpy as np
import pytest

from scripts.modeling.inductive_profiles_v8 import KernelGeometry, inductive_profile


@pytest.mark.parametrize("kind", ["linear", "rbf", "mixed"])
def test_query_is_not_used_to_fit_kernel(kind):
    rng = np.random.default_rng(42)
    x, z = rng.normal(size=(15, 4)), rng.normal(size=(3, 4))
    a = KernelGeometry(x, z, kind)
    b = KernelGeometry(x, np.concatenate([z, np.full((2, 4), 1000)]), kind)
    np.testing.assert_allclose(a.k, b.k)
    np.testing.assert_allclose(a.cross, b.cross[:len(z)])
    assert np.min(a.eig) >= 0


def test_full_rank_matches_ridge():
    rng = np.random.default_rng(42)
    x, z = rng.normal(size=(15, 4)), rng.normal(size=(3, 4))
    r = rng.normal(size=(15, 8))
    r -= r.mean(axis=1, keepdims=True)
    g = KernelGeometry(x, z, "linear")
    lam = .3
    expected = r.mean(axis=0) + g.cross @ np.linalg.solve(
        g.k + lam * np.eye(len(x)), r - r.mean(axis=0)
    )
    actual = inductive_profile(g, r, lam, 0)
    np.testing.assert_allclose(actual, expected, atol=1e-10)


def test_rank_and_masked_completion():
    rng = np.random.default_rng(42)
    x, z = rng.normal(size=(20, 5)), rng.normal(size=(8, 5))
    r = rng.normal(size=(20, 10))
    r[0, 0] = np.nan
    g = KernelGeometry(x, z, "rbf")
    pred = inductive_profile(g, r, .3, 3, 3)
    assert np.isfinite(pred).all()
    assert np.linalg.matrix_rank(pred - pred.mean(axis=0), tol=1e-10) <= 3
    np.testing.assert_allclose(pred.mean(axis=1), 0, atol=1e-10)

import numpy as np
import pandas as pd

from scripts.modeling.hybrid_gp_v107 import correction, object_kernel, posterior, spectral_factor


def test_kernel_psd():
    k, q = object_kernel([{"a": 1.}, {"b": 2.}, {"a": .5}], {"a": .2}, "mixed")
    assert np.linalg.eigvalsh(k).min() > -1e-10
    assert q.shape == (3,)


def test_separable_mean_matches_dense_gp():
    k = np.array([[1., .4], [.4, 1.]])
    cross = np.array([.2, .6])
    r = np.array([[.1, -.1, 0.], [.2, .1, -.3]])
    u, s = spectral_factor(np.array([[1., 0.], [0., 1.], [0., 1.]]))
    g = np.eye(3) + (u * s) @ u.T
    noise = .7
    dense = np.kron(cross.reshape(1, -1), g) @ np.linalg.solve(
        np.kron(k, g) + noise * np.eye(6), r.ravel())
    np.testing.assert_allclose(posterior(k, cross, r, (u, s), noise), dense)


def test_strict_prior_and_warmup():
    day = pd.Timestamp("2020-02-01")
    factors = {"identity": (np.empty((3, 0)), np.empty(0))}
    prior = [(pd.Timestamp("2020-01-01") + pd.Timedelta(days=i), {"a": 1.},
              np.array([.1, -.1, 0.])) for i in range(8)]
    a, n = correction(prior, day, {"a": 1.}, factors, "mixed", "identity", 1.)
    b, m = correction(prior + [(day, {"a": 1.}, np.ones(3)*100)],
                      day, {"a": 1.}, factors, "mixed", "identity", 1.)
    assert n == m == 8
    np.testing.assert_array_equal(a, b)
    warm, _ = correction(prior[:7], day, {"a": 1.}, factors, "mixed", "identity", 1.)
    np.testing.assert_array_equal(warm, np.zeros(3))

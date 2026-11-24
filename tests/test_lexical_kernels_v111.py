"""V11.1 tests for fixed-kernel historical profile prediction."""
import numpy as np

from scripts.modeling.lexical_kernels_v111 import (
    blend_kernels,
    centered_krr,
    full_reconstruct,
    lexical_kernel,
    structured_kernel,
)


def test_constant_target_preserved():
    x = np.array([[0.], [1.], [3.]])
    k, q = structured_kernel(x, np.array([[2.]]))
    np.testing.assert_allclose(centered_krr(k, q, np.full((3, 2), .4)), [[.4, .4]])


def test_lexical_vocabulary_uses_only_training_documents():
    docs = ["taxation sociale", "taxation des entreprises", "droit social"]
    a, b = lexical_kernel(docs, ["taxation uniquequefuture", "zzzz"], "word")
    a2, b2 = lexical_kernel(docs, ["taxation"], "word")
    np.testing.assert_allclose(a, a2)
    np.testing.assert_allclose(b[0], b2[0])
    np.testing.assert_allclose(b[1], 0.)


def test_hybrid_is_positive_semidefinite():
    a = structured_kernel(np.arange(4.)[:, None], np.array([[1.]]))
    b = lexical_kernel(["alpha beta", "alpha gamma", "beta gamma", "alpha beta"], ["alpha beta"], "word")
    k, q = blend_kernels(a, b, .5)
    assert np.linalg.eigvalsh(k).min() >= -1e-9
    assert q.shape == (1, 4)


def test_unseen_municipality_has_only_predicted_mean():
    h = np.array([[.5, -.2, .1], [.6, .1, -.1]])
    np.testing.assert_allclose(full_reconstruct(h, np.array([0, 0, 1]), np.array([0, -1, 1])), [.3, .5, .5])

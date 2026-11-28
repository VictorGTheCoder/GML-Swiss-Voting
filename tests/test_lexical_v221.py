import numpy as np
import pandas as pd
import pytest

from scripts.modeling.lexical_v221 import supervised_text


def sample():
    return pd.DataFrame({
        "document_text": ["alpha alpha beta", "alpha gamma beta", "beta delta gamma",
                          "delta epsilon gamma", "alpha epsilon zeta", "beta zeta delta",
                          "alpha delta epsilon", "gamma epsilon zeta", "unknown token alpha",
                          "delta beta zeta"],
        "usable_summary": [True] * 10,
        "vote_date": pd.date_range("2010-01-01", periods=10),
    }, index=[str(i) for i in range(10)])


def test_train_only_and_shape():
    doc = sample()
    ids, queries = list(doc.index[:8]), list(doc.index[8:])
    y = np.random.default_rng(42).normal(size=(8, 6))
    a, b = supervised_text(doc, ids, queries, y)
    assert a.shape == (8, 7) and b.shape == (2, 7)
    assert np.isfinite(a).all() and np.isfinite(b).all()
    doc.loc[queries[1], "document_text"] = "completely different vocabulary"
    c, d = supervised_text(doc, ids, queries, y)
    np.testing.assert_allclose(a, c)
    np.testing.assert_allclose(b[0], d[0])


def test_reject_overlap_and_future():
    doc = sample()
    ids = list(doc.index[:8])
    y = np.ones((8, 6))
    with pytest.raises(ValueError):
        supervised_text(doc, ids, [ids[0]], y)
    doc.loc["8", "vote_date"] = pd.Timestamp("2009-01-01")
    with pytest.raises(ValueError):
        supervised_text(doc, ids, ["8"], y)


def test_zero_cross_covariance():
    doc = sample()
    a, b = supervised_text(doc, list(doc.index[:8]), list(doc.index[8:]), np.ones((8, 6)))
    np.testing.assert_allclose(a[:, :6], 0)
    np.testing.assert_allclose(b[:, :6], 0)

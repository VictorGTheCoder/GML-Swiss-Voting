"""Tests of V12.3 matched support and chronological feature isolation."""

import numpy as np
import pandas as pd

from scripts.modeling.views_v123 import block_features, make_documents, view_features


def test_views_cannot_admit_new_documents():
    audit = pd.DataFrame({
        "title_text": ["Titre A", "Titre B", "Titre C"],
        "vote_date": pd.to_datetime(["2020-01-01"] * 3),
        "original_text": ["old", "old", ""],
        "original_covered": [True, True, False],
        "exact_text": [
            "Acceptez-vous cette modification de la loi fédérale ?",
            "",
            "Acceptez-vous une nouvelle initiative populaire ?",
        ],
    }, index=["a", "b", "c"])
    docs = make_documents(audit)
    for doc in docs.values():
        assert doc.usable_summary.tolist() == [True, False, False]
        assert doc.loc["b", "body"] == doc.loc["c", "body"] == ""
        assert doc.loc["b", "question"] == doc.loc["c", "question"] == ""
        assert doc.loc["a", "question"]


def test_training_representation_independent_of_query():
    train = ["loi fédérale suisse", "loi fédérale fiscale", "loi fiscale suisse"]
    a, b = block_features(train, ["loi fédérale suisse"], 4)
    c, d = block_features(train, ["zzzzz"], 4)
    assert a.shape == c.shape == (3, 4)
    assert b.shape == d.shape == (1, 4)
    np.testing.assert_allclose(a, c)
    np.testing.assert_allclose(block_features(["", ""], ["new"], 4)[1], 0)


def test_split_budget_and_coverage():
    doc = pd.DataFrame({
        "title_text": ["loi fédérale", "loi fiscale", "loi suisse", "loi nouvelle"],
        "body": ["loi fédérale suisse", "loi fiscale suisse", "", ""],
        "question": ["", "", "", ""],
        "mechanism": ["", "", "", ""],
        "usable_summary": [True, True, False, False],
    }, index=["a", "b", "c", "d"])
    for name in ("split_title_body", "split_question_mechanism"):
        a, b = view_features(doc, ["a", "b", "c"], ["d"], name)
        assert a.shape == (3, 17) and b.shape == (1, 17)
        assert np.isfinite(a).all() and np.isfinite(b).all()
        assert b[0, -1] == 0
        assert a[:, -1].tolist() == [1, 1, 0]

"""V12.3: equal-dimensional, coverage-matched documentary views."""

from __future__ import annotations

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

from scripts.modeling.coverage_v121 import matched_documents
from scripts.modeling.documentary_audit_v112 import mechanism_text, question_text
from scripts.modeling.remaining_priorities_v9 import text_features

CONFIGS = ("pooled_exact", "split_title_body", "split_question_mechanism")
VIEWS = {
    "split_title_body": (("title_text", 4), ("body", 12)),
    "split_question_mechanism": (
        ("title_text", 4), ("body", 4), ("question", 4), ("mechanism", 4),
    ),
}


def make_documents(audit):
    """Freeze the common V12.1 support; never admit newly recovered pages."""
    doc = matched_documents(audit)["matched_exact"]
    doc["body"] = audit.exact_text.where(doc.usable_summary, "")
    doc["question"] = doc.body.map(question_text)
    doc["mechanism"] = doc.body.map(mechanism_text)
    return {name: doc for name in CONFIGS}


def block_features(train, query, n):
    """Learn vocabulary, SVD and scaling from past objects only.

    Absent or rank-deficient views are zero-padded to the fixed feature budget.
    """
    a = np.zeros((len(train), n))
    b = np.zeros((len(query), n))
    if len(train) < 2 or not any(str(t).strip() for t in train):
        return a, b
    vectorizer = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 5), min_df=2,
        max_features=12000, sublinear_tf=True,
    )
    try:
        x = vectorizer.fit_transform(train)
    except ValueError as exc:
        if "empty vocabulary" not in str(exc) and "no terms remain" not in str(exc).lower():
            raise
        return a, b
    rank = min(n, x.shape[0] - 1, x.shape[1] - 1)
    if rank < 1:
        return a, b
    svd = TruncatedSVD(n_components=rank, random_state=20261124)
    aa = svd.fit_transform(x)
    bb = svd.transform(vectorizer.transform(query))
    mean = aa.mean(axis=0)
    scale = aa.std(axis=0).clip(min=1e-8)
    a[:, :rank] = (aa - mean) / scale
    b[:, :rank] = (bb - mean) / scale
    return a, b


def view_features(doc, train_ids, query_ids, name):
    if name == "pooled_exact":
        return text_features(doc, train_ids, query_ids, "tfidf_document", 16)
    train, query = doc.loc[train_ids], doc.loc[query_ids]
    pairs = [block_features(train[field], query[field], n) for field, n in VIEWS[name]]
    return (
        np.column_stack([*(a for a, _ in pairs), train.usable_summary.to_numpy(float)]),
        np.column_stack([*(b for _, b in pairs), query.usable_summary.to_numpy(float)]),
    )

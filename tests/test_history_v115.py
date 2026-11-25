import numpy as np
import pandas as pd
import pytest

from scripts.modeling.history_v115 import audit_history, basis_for_history, export_document_roster


def rows():
    return pd.DataFrame({"vote_id": ["a", "a", "b", "c", "c"],
                         "municipality_id": ["1", "2", "1", "1", "2"],
                         "canton": ["A", "B", "A", "A", "B"],
                         "vote_date": pd.to_datetime(["1985-01-01", "1985-01-01",
                                                     "1986-01-01", "1970-01-01", "1970-01-01"])})


def test_coverage_and_era():
    _, audit = audit_history(rows(), pd.Series({"1": "A", "2": "B"}))
    assert audit.eligible.tolist() == [True, False, False]
    assert audit.min_canton_coverage.tolist() == [1., 0., 1.]


def test_duplicate_and_future_rejected():
    a = rows()
    with pytest.raises(ValueError, match="Duplicate"):
        audit_history(pd.concat([a, a]), pd.Series({"1": "A", "2": "B"}))
    with pytest.raises(ValueError, match="predate"):
        audit_history(a.assign(vote_date=pd.Timestamp("1990-01-01")),
                      pd.Series({"1": "A", "2": "B"}))


def test_older_basis_only_modern_heads():
    rng = np.random.default_rng(2)
    m, o = rng.normal(size=(12, 8)), rng.normal(size=(6, 8))
    mu = np.linspace(.2, .8, 12)
    dates = pd.date_range("2000-01-01", periods=12, freq="D")
    older = pd.date_range("1985-01-01", periods=6, freq="D")
    basis, heads = basis_for_history(m, mu, dates, o, older, "2016-01-01", 5, 2)
    assert heads.shape == (12, 6)
    np.testing.assert_allclose(heads[:, 0], mu)
    np.testing.assert_allclose(heads[:, 1:], (m - basis.mean_) @ basis.components_.T)
    with pytest.raises(ValueError, match="strictly precede"):
        basis_for_history(m, mu, dates, o, older, "1985-01-01", 5, 2)


def test_document_roster_is_not_historical_audit(tmp_path):
    document = pd.DataFrame({name: ["text"] for name in (
        "original_text", "exact_text", "multi_text", "question_text", "mechanism_text")},
        index=pd.Index(["vote-a"], name="vote_id"))
    document["source"] = "official"
    _, historical = audit_history(rows(), pd.Series({"1": "A", "2": "B"}))
    path = tmp_path / "audit_roster.csv"
    export_document_roster(document, path)
    assert pd.read_csv(path).to_dict("records") == [{"vote_id": "vote-a", "source": "official"}]
    with pytest.raises(KeyError):
        export_document_roster(historical, path)

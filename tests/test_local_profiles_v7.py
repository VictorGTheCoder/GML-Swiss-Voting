"""V7 local-weight and representative-panel invariants."""
import numpy as np
import pandas as pd
import pytest

from scripts.modeling.local_profiles_v7 import (
    metric_basis,
    panel_eval,
    representative_errors,
    representative_rank,
    similarity_sample_weights,
)


def synthetic():
    rows = []
    for vote in range(40):
        for name, yes, no in [("001", 50, 50), ("002", 80, 20), ("003", 20, 80)]:
            rows.append({
                "vote_id": str(vote), "municipality_id": name,
                "canton": "A", "votes_yes": yes, "votes_no": no,
            })
    return pd.DataFrame(rows)


def test_representative_errors_exclude_own_ballots():
    rows = synthetic()
    a = representative_errors(rows, "national")
    selected = a[(a.vote_id == "0") & (a.municipality_id == "002")].iloc[0]
    assert selected.rest_share == pytest.approx(.35)
    assert selected.error == pytest.approx(.45)
    rank = representative_rank(rows, "national").set_index("municipality_id")
    assert rank.loc["001", "mae"] == pytest.approx(0)
    assert rank.loc["001", "weight"] > rank.loc["002", "weight"]
    assert rank.weight.mean() == pytest.approx(1)


def test_single_commune_canton_is_unknown_not_perfect():
    rows = synthetic()
    rows.loc[rows.municipality_id.eq("001"), "canton"] = "B"
    rank = representative_rank(rows, "canton").set_index("municipality_id")
    assert not rank.loc["001", "eligible"]
    assert pd.isna(rank.loc["001", "mae"])
    assert rank.loc["001", "weight"] == 1


def test_panel_selection_frozen_from_train():
    train = synthetic()
    rank = representative_rank(train, "national")
    test = train[train.vote_id.eq("0")].copy()
    test["vote_id"] = "future"
    result = panel_eval(rank, test, "national", np.random.default_rng(42))
    assert len(result) == 1
    assert result[0]["panel_ids"] == "001"
    assert result[0]["panel_error_pp"] == pytest.approx(0)
    assert result[0]["random_error_pp"] > 0


def test_weighted_basis_full_rank_recovers_original_units():
    r = np.array([[-.2, .1, .1], [.1, .1, -.2], [.2, -.3, .1], [-.1, .1, 0.]])
    mu = np.array([.4, .5, .6, .7])
    basis, heads = metric_basis(
        r, mu, np.array([.5, 1., 1.5, 2.]), np.array([.5, 1., 2.]), 2, 42
    )
    np.testing.assert_allclose(heads[:, 0], mu)
    np.testing.assert_allclose(basis.mean_[None, :] + heads[:, 1:] @ basis.components_, r, atol=1e-10)


def test_similarity_weights_remain_positive_and_normalized():
    w = similarity_sample_weights(np.array([0., .5, 1.]))
    assert np.all(w > 0)
    assert w.mean() == pytest.approx(1)
    assert w[2] / w[0] == pytest.approx(4)
    with pytest.raises(ValueError):
        similarity_sample_weights(np.array([-1., .5, 1.]))

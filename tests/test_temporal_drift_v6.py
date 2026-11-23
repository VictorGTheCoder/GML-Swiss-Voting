"""Leakage guards and recency weighting contracts."""
import numpy as np
import pandas as pd
import pytest

from scripts.modeling.temporal_drift_v6 import (
    DOMAIN,
    effective_n,
    matching_weights,
    recency_weights,
    trend_features,
    weighted_profile,
)


def meta(dates, ids):
    return pd.DataFrame({
        "vote_date": pd.to_datetime(dates),
        DOMAIN[0]: ["4"] * len(ids),
        DOMAIN[1]: [None] * len(ids),
        DOMAIN[2]: [None] * len(ids),
        "political_direction_ps": [1.0] * len(ids),
    }, index=ids)


def test_half_life_and_normalization():
    dates = ["2000-01-01", "2010-01-01"]
    w = recency_weights(dates, "2020-01-01", 10)
    assert w[1] / w[0] == pytest.approx(2, abs=0.002)
    assert w.mean() == pytest.approx(1)
    assert effective_n(w) < 2
    np.testing.assert_array_equal(recency_weights(dates, "2020-01-01", None), [1, 1])
    with pytest.raises(ValueError):
        recency_weights(dates, "2010-01-01", 10)
    with pytest.raises(ValueError):
        recency_weights(dates, "2020-01-01", 0)


def test_trends_exclude_same_day_future_and_query_outcomes():
    history = meta(["2005-01-01", "2014-01-01", "2016-01-01", "2017-01-01"],
                   ["old", "recent", "same", "future"])
    labels = pd.DataFrame({"mean_yes": [.3, .6, .99, .01], "fr_de": [-.1, .1, .8, -.8]},
                          index=history.index)
    query = meta(["2016-01-01"], ["query"])
    directions = ["political_direction_ps"]
    result = trend_features(query, history, labels, directions, "history")
    assert result.loc[0, "time_recent_mean_yes"] == pytest.approx(.6)
    assert result.loc[0, "time_delta_mean_yes"] == pytest.approx(.3)
    assert result.loc[0, "time_similar_delta_fr_de"] == pytest.approx(.2)
    labels.loc[["same", "future"], :] = .42
    pd.testing.assert_frame_equal(result, trend_features(query, history, labels, directions, "history"))
    with pytest.raises(ValueError):
        trend_features(query.assign(yes_share=.5), history, labels, directions, "history")


def test_similarity_not_treating_unknown_as_no():
    prior = meta(["2010-01-01"] * 3, ["same", "opp", "unrelated"])
    prior.loc["opp", "political_direction_ps"] = -1
    prior.loc["unrelated", DOMAIN[0]] = "6"
    q = meta(["2015-01-01"], ["q"]).iloc[0]
    np.testing.assert_allclose(matching_weights(prior, q, ["political_direction_ps"]), [1, .25, 0])


def test_weighted_pca_preserves_object_means_and_shape():
    rows = pd.DataFrame({
        "vote_id": ["a", "a", "b", "b", "c", "c"],
        "municipality_id": ["001", "002"] * 3,
        "yes_share": [.2, .4, .3, .7, .8, .2],
    })
    fold = {"train_ids": ["a", "b", "c"],
            "heads": np.array([[.3, 0], [.5, 0], [.5, 0]])}
    pca, heads = weighted_profile(fold, rows, np.array([.5, 1, 1.5]),
                                  {"dimensions": 1, "random_state": 1})
    np.testing.assert_allclose(heads[:, 0], [.3, .5, .5])
    residual = rows.pivot(index="vote_id", columns="municipality_id", values="yes_share").to_numpy(copy=True)
    residual -= residual.mean(axis=1)[:, None]
    np.testing.assert_allclose(pca.mean_[None, :] + heads[:, 1:] @ pca.components_, residual, atol=1e-12)

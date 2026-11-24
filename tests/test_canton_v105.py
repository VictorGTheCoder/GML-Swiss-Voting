import numpy as np
import pandas as pd

from scripts.modeling.canton_v105 import aggregate, apply_targets, direct_forecasts, feature_map, prior_cantons


def test_prior_only():
    history = pd.DataFrame([
        {"vote_id": str(i), "vote_date": pd.Timestamp("2010-01-01") + pd.Timedelta(days=i),
         "canton": c, "share": s, "contrast": s - .5, "object_domain_1": "x"}
        for i in range(25) for c, s in (("a", .3), ("b", .7))
    ])
    day = pd.Timestamp("2011-01-01")
    a, n = direct_forecasts(history, day, {"object_domain_1": "x"}, ["a", "b"])
    changed = pd.concat([history, pd.DataFrame([
        {"vote_id": "future", "vote_date": day, "canton": "a", "share": 1., "contrast": .5}
    ])], ignore_index=True)
    b, m = direct_forecasts(changed, day, {"object_domain_1": "x"}, ["a", "b"])
    assert n == m == 25
    np.testing.assert_allclose(a["absolute"], b["absolute"])
    np.testing.assert_allclose(a["centered"], b["centered"])
    assert a["absolute"][0] < a["absolute"][1]


def test_canton_target_and_bounds():
    p = np.array([.1, .4, .8, .9])
    w = np.array([1., 4., 3., 2.])
    c = np.array(["a", "a", "b", "b"])
    q = apply_targets(p, w, c, ["a", "b"], [.9, .1], 1.)
    np.testing.assert_allclose(aggregate(q, w, c, ["a", "b"]), [.9, .1], atol=1e-8)
    assert np.all((q >= 0) & (q <= 1))


def test_features_exclude_target():
    assert feature_map("a", {"yes_share": 1., "votes_yes": 42}) == feature_map("a", {})


def test_canton_lookup_uses_only_prior_geography():
    day = pd.Timestamp("2016-01-01")
    geo = pd.DataFrame({
        "municipality_id": ["a", "b", "a"],
        "canton": ["VD", "ZH", "XX"],
        "vote_date": [day - pd.Timedelta(days=1), day - pd.Timedelta(days=1), day],
    })
    assert prior_cantons(geo, day, ["b", "a"]).tolist() == ["ZH", "VD"]

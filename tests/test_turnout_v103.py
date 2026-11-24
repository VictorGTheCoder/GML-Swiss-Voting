import numpy as np
import pandas as pd

from scripts.modeling.turnout_v103 import history_weights


def fixture():
    return pd.DataFrame({
        "municipality_id": ["a", "b", "a", "b"],
        "vote_date": pd.to_datetime(["2018-01-01", "2018-01-01", "2019-01-01", "2019-01-01"]),
        "eligible_voters": [100., 200., 999., 999.],
        "ballots_cast": [50., 80., 999., 999.],
        "votes_yes": [25., 35., 500., 500.],
        "votes_no": [20., 40., 499., 499.],
        "domain": ["x", "x", "x", "x"],
    })


def test_strict_date_exclusion():
    h = fixture()
    args = (pd.Timestamp("2019-01-01"), ["a", "b"], np.array([100., 200.]), "x")
    w, rate, known, _ = history_weights(h, *args)
    np.testing.assert_allclose(w["eligible"], [100, 200])
    np.testing.assert_allclose(w["last"], [45, 75])
    np.testing.assert_allclose(rate["turnout"]["last"], [.5, .4])
    assert known.all()
    h.loc[h.vote_date.eq("2019-01-01"), "votes_yes"] = 0.
    changed, _, _, _ = history_weights(h, *args)
    for k in w:
        np.testing.assert_allclose(w[k], changed[k])


def test_missing_municipality_fallback():
    w, _, known, dn = history_weights(fixture(), pd.Timestamp("2019-01-01"),
                                      ["a", "b", "c"], np.array([100., 200., 50.]), "y")
    np.testing.assert_allclose(w["eligible"], [100, 200, 50])
    assert known.tolist() == [True, True, False]
    assert (dn == 0).all()
    for values in w.values():
        assert (values > 0).all()


def test_domain_shrinkage():
    w, rates, _, dn = history_weights(fixture(), pd.Timestamp("2019-01-01"),
                                      ["a", "b"], np.array([100., 200.]), "x")
    assert (dn == 1).all()
    assert np.all((rates["valid_rate"]["domain"] > 0) & (rates["valid_rate"]["domain"] < 1))
    assert not np.array_equal(w["domain"], w["pooled"])

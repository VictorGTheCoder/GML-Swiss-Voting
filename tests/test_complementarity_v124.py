"""Tests for date isolation and level/contrast combinations."""
import numpy as np
import pandas as pd

from scripts.modeling.complementarity_v124 import date_sensitivity, date_weights, forecasts


def test_same_day_history_has_no_effect():
    day = pd.Timestamp("2020-01-01")
    history = [{"date": day - pd.Timedelta(days=i + 1),
                "national": np.eye(2), "local": np.eye(2)} for i in range(8)]
    a, b, n = date_weights(history, day)
    c, d, m = date_weights(history + [{"date": day, "national": np.ones((2, 2)) * 100,
                                      "local": np.ones((2, 2)) * 100}], day)
    np.testing.assert_allclose(a, c)
    np.testing.assert_allclose(b, d)
    assert n == m == 8


def test_level_combinations_reconcile():
    x = np.array([[.2, .8], [.4, .7], [.5, .6]])
    w = np.array([1., 2., 4.])
    f = forecasts(x, w, [.5, .5], [.5, .5])
    np.testing.assert_allclose(np.average(f["pooled_level_institution_local"], weights=w),
                               np.average(x[:, 1], weights=w), atol=1e-7)
    np.testing.assert_allclose(np.average(f["institution_level_pooled_local"], weights=w),
                               np.average(x[:, 0], weights=w), atol=1e-7)
    np.testing.assert_allclose(f["fixed_half"], f["adaptive_split"], atol=1e-7)


def test_date_sensitivity_drops_all_objects_on_date():
    rows = []
    for day, vote, gain in [("a", "1", 1.), ("a", "2", 3.), ("b", "3", 9.)]:
        rows.extend([{"vote_date": day, "vote_id": vote, "variant": "ref", "mae_pp": gain},
                     {"vote_date": day, "vote_id": vote, "variant": "candidate", "mae_pp": 0.}])
    got = date_sensitivity(pd.DataFrame(rows), "candidate", "ref")
    assert got == [{"excluded_date": "a", "gain_pp": 9.},
                   {"excluded_date": "b", "gain_pp": 2.}]

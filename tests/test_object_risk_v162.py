import numpy as np
import pandas as pd
import pytest

from scripts.modeling.object_risk_v162 import calibrate, summarize, upper


def panel():
    dates = pd.date_range("2016-01-01", periods=12, freq="MS")
    return pd.DataFrame([{"vote_date": d, "vote_id": f"{i}-{j}",
                          "mae_pp": float(i + j)}
                         for i, d in enumerate(dates) for j in range(1 + i % 3)])


def test_rank_and_small_sample():
    assert upper(range(1, 10), .9) == 9
    with pytest.raises(ValueError):
        upper([1, 2], .9)


def test_all_methods_and_dates():
    out = calibrate(panel())
    assert len(summarize(out)) == 12
    assert out.vote_date.nunique() == 3
    assert out.training_dates.min() == 9
    for _, g in out.groupby(["level", "mode", "vote_date"]):
        b = g.groupby("method").bound_pp.first()
        assert b.date_max >= b.date_mean


def test_same_date_and_future_targets_do_not_change_bounds():
    p = panel()
    before = calibrate(p)
    cutoff = p.vote_date.unique()[10]
    p.loc[p.vote_date.ge(cutoff), "mae_pp"] = 99.
    after = calibrate(p)
    mask = before.vote_date.le(str(pd.Timestamp(cutoff).date()))
    np.testing.assert_array_equal(before.loc[mask, "bound_pp"], after.loc[mask, "bound_pp"])


def test_fixed_constant_and_expanding_counts():
    out = calibrate(panel())
    for _, g in out[out["mode"].eq("fixed")].groupby(["level", "method"]):
        assert g.bound_pp.nunique() == 1
        assert g.training_dates.unique().tolist() == [9]
    assert set(out[out["mode"].eq("expanding")].training_dates) == {9, 10, 11}


@pytest.mark.parametrize("corruption", ["future", "duplicate", "nan", "negative"])
def test_reject_invalid_panel(corruption):
    p = panel()
    if corruption == "future":
        p.loc[0, "vote_date"] = pd.Timestamp("2023-01-01")
    elif corruption == "duplicate":
        p.loc[1, "vote_id"] = p.loc[0, "vote_id"]
    elif corruption == "nan":
        p.loc[0, "mae_pp"] = np.nan
    else:
        p.loc[0, "mae_pp"] = -1
    with pytest.raises(ValueError):
        calibrate(p)

import numpy as np
import pandas as pd
import pytest

from scripts.modeling.error_budget_v133 import date_interval, offset_diagnosis


def test_constant_bias_oracle():
    result = offset_diagnosis([.2, .4, .6], [.3, .5, .7])
    assert result["mae_pp"] == pytest.approx(10)
    assert result["median_offset_oracle_pp"] == pytest.approx(0)


def test_median_oracle_optimal_and_separate():
    y = np.array([.2, .2, .2, .2, .2])
    p = np.array([.2, .2, .2, .2, .8])
    result = offset_diagnosis(y, p)
    assert result["median_offset_oracle_pp"] == pytest.approx(12)
    assert result["centered_mae_pp"] == pytest.approx(19.2)
    for shift in np.linspace(-1, 1, 201):
        assert result["median_offset_oracle_pp"] <= 100 * np.abs(p + shift - y).mean() + 1e-9


def test_bootstrap_keeps_dates_and_reproducible():
    detail = pd.DataFrame({"vote_date": ["a", "a", "b"], "gain": [0., 0., 9.]})
    assert date_interval(detail, "gain") == date_interval(detail, "gain")
    assert date_interval(detail, "gain") == pytest.approx([0., 9.])


def test_invalid_share():
    with pytest.raises(ValueError):
        offset_diagnosis([.1], [1.1])

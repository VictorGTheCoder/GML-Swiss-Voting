import numpy as np
import pandas as pd
import pytest

from scripts.modeling.rolling_v163 import blended_anchor, date_windows, fit_structural_weight, split_date


def test_date_grouping_and_forbidden():
    data = pd.DataFrame({"vote_date": pd.to_datetime(["2019-01-01", "2020-01-01", "2020-01-01"])})
    tr, ev = split_date(data, date_windows(data.vote_date)[1]["start"])
    assert len(tr) == 1 and len(ev) == 2
    with pytest.raises(ValueError):
        date_windows(["2023-01-01"])


def test_regularized_weight_and_cold_start():
    block = [(0.4, 0.6, 0.6)]
    assert fit_structural_weight([block] * 3) == 0.
    expected = (4 * .2 ** 2) / (4 * .2 ** 2 + 8 * .08 ** 2)
    assert fit_structural_weight([block] * 4) == pytest.approx(expected)
    assert fit_structural_weight([block * 5] * 4) == pytest.approx(expected)
    assert fit_structural_weight([[(0.4, 0.6, 0.2)]] * 4) == 0.


def test_date_block_calibration():
    blocks = [[(.4, .6, .6)]] * 4
    before = fit_structural_weight(blocks)
    later = blocks + [[(.4, .6, .2), (.4, .6, .2)]]
    assert fit_structural_weight(later[:-1]) == before
    assert fit_structural_weight(later) < before


def test_blend_level_and_no_poll_fallback():
    v = pd.DataFrame({"weight": [1., 3.], "poll_available": [True, True],
                      "language": ["other", "other"], "urban": ["other", "other"]})
    f = pd.DataFrame({"v8_reference": [.4, .4]})
    p = np.array([.4, .8])
    for weight in (0., .25, 1.):
        q = blended_anchor(p, v, f, None, None, weight)
        assert np.average(q, weights=v.weight) == pytest.approx(.4 + weight * .3)
        assert np.all((q >= 0.) & (q <= 1.))
    v["poll_available"] = False
    assert np.allclose(blended_anchor(p, v, f, None, None, .25), p)

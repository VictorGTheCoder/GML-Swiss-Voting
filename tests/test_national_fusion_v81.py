"""Stage 02 national ensemble invariants."""

import numpy as np
import pandas as pd
import pytest

from scripts.modeling.national_fusion_v81 import fit_fusion, pair_forecast, target_table


def test_fusion_shrunk_to_equal_weight_until_enough_history():
    w,b = fit_fusion([[.1,-.1]]*7)
    assert w==.5
    np.testing.assert_array_equal(b,[0,0])
    w,_ = fit_fusion([[.01,.2]]*30)
    assert .5<w<=.9
    w,_ = fit_fusion([[.2,.01]]*30)
    assert .1<=w<.5


def test_pair_forecast_caps_and_cutoff():
    a = pd.Series({"first_midpoint":"2016-01-01","last_midpoint":"2016-02-01",
                   "last_published_date":"2016-02-10","last_yes":40,"first_yes":80})
    last,delta=pair_forecast(a,"2016-02-28")
    assert last==.4
    assert delta==pytest.approx(-.15)
    with pytest.raises(ValueError):
        pair_forecast(a,"2016-02-10")


def test_tamedia_only_never_creates_ssr():
    w=(fit_fusion([]),fit_fusion([],use_bias=True))
    r=target_table(.4,None,0.,.6,w,.4)
    assert r["ssr_extended"]==.4
    assert r["ssr_extended_tamedia_fallback"]==.6
    assert r["blend50"]==.6


def test_blend_has_bounded_targets_and_reference_preserved():
    w=(fit_fusion([]),fit_fusion([],use_bias=True))
    r=target_table(.4,.5,-.1,.6,w,.3)
    assert r["v8_reference"]==.4
    assert r["ssr_extended"]==.4
    assert r["blend50"]==pytest.approx(.5)
    assert all(0<=v<=1 for v in r.values())

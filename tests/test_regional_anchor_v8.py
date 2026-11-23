"""Regional margins: coherence, uncertainty and chronology."""
import numpy as np
import pandas as pd
import pytest

from scripts.modeling.regional_anchor_v8 import (
    LANGUAGES,
    gap_adjust,
    group_stats,
    regional_target,
    shift_to,
)


def test_bounded_anchor_preserves_weighted_mean():
    p = np.array([.02, .1, .9, .98])
    w = np.array([1., 2., 3., 4.])
    adjusted = shift_to(p, w, .75)
    assert np.average(adjusted, weights=w) == pytest.approx(.75)
    assert np.all((adjusted >= 0) & (adjusted <= 1))


def test_regional_gap_maintains_national_anchor_and_uncovered_area():
    p = np.array([.4, .5, .5, .6, .6, .7, .3])
    w = np.arange(1, 8, dtype=float)
    groups = np.array(["de", "de", "fr", "fr", "it", "it", "other"])
    target = np.array([.2, .8, .4])
    adjusted = gap_adjust(p, w, groups, LANGUAGES, target, 1)
    assert np.average(adjusted, weights=w) == pytest.approx(np.average(p, weights=w))
    assert adjusted[-1] == p[-1]
    _, regional = group_stats(adjusted, w, groups, LANGUAGES)
    np.testing.assert_allclose(regional - regional[0], target - target[0], atol=1e-10)


def test_future_published_wave_excluded():
    a = pd.DataFrame({
        "wave": [1]*3 + [2]*3, "region": list(LANGUAGES)*2,
        "yes_total": [40,50,60,99,99,99],
        "no_total": [50,40,30,0,0,0], "undecided": [10]*3+[1]*3,
        "survey_midpoint": ["2021-01-01"]*3+["2021-02-01"]*3,
        "published_at": ["2021-01-10T06:00:00Z"]*3+["2021-03-07T06:00:00Z"]*3,
    })
    np.testing.assert_allclose(regional_target(a, "2021-03-07", 1, "yes"), [.4,.5,.6])

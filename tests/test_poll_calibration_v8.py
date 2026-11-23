"""Small-sample calibration safeguards."""
import numpy as np
import pandas as pd

from scripts.modeling.poll_calibration_v8 import fit_national, fit_regional, prior_poll_data


def test_insufficient_history_reproduces_original_prior():
    x, bias = fit_national([])
    np.testing.assert_array_equal(x, [0, 1, 0])
    assert bias == 0
    slope, intercept = fit_regional([])
    assert slope == 1
    np.testing.assert_array_equal(intercept, [0, 0, 0])


def test_bounded_fit_uses_only_passed_history():
    history = [{"yes": .4, "undecided": .1, "delta": -.02,
                "actual": .5, "frozen": .38} for _ in range(15)]
    x, bias = fit_national(history)
    assert -.15 <= x[0] <= .15
    assert 0 <= x[1] <= 1.5
    assert 0 <= x[2] <= 1
    assert bias > 0


def test_publication_cutoff_blocks_late_wave():
    rows = pd.DataFrame({
        "wave":[1,2], "yes_total":[40,99], "no_total":[50,0],
        "undecided":[10,1], "published_at":["2021-01-10T06:00:00Z","2021-03-07T06:00:00Z"],
        "survey_midpoint":["2021-01-01","2021-02-25"],
    })
    r = prior_poll_data(rows, pd.Timestamp("2021-03-07"))
    assert r["yes"] == .4
    assert r["delta"] == 0

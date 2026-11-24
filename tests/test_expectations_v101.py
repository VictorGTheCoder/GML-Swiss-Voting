"""V10.1 checks: expected share provenance and aggregate scoring."""
import numpy as np
import pandas as pd
import pytest

from scripts.modeling.expectations_v101 import apply_expectation, blend_weight, multiscale, validate_expectations


def test_expectation_anchor_and_fallback():
    p, w = np.array([.2, .8]), np.array([1., 2.])
    q = apply_expectation(p, w, .4, .5)
    assert np.average(q, weights=w) == pytest.approx(.5)
    np.testing.assert_array_equal(apply_expectation(p, w, None, 1.), p)
    np.testing.assert_array_equal(apply_expectation(p, w, .4, 0.), p)


def test_small_sample_blend_needs_three_earlier_dates():
    assert blend_weight([("a", .6, .4, .4)] * 20) == .5
    h = [(str(i // 4), .6, .4, .4) for i in range(24)]
    assert blend_weight(h) > .5


def test_multiscale_predictions_use_ex_ante_weights_not_ballots():
    y = np.array([.2, .8, .5])
    p = np.array([.4, .4, .5])
    w = np.array([1., 3., 2.])
    yes, no = np.array([20., 8., 10.]), np.array([80., 2., 10.])
    m, c = multiscale(y, p, w, yes, no, ["A", "A", "B"])
    assert m["national_prediction"] == pytest.approx(2.6 / 6)
    assert m["national_observed"] == pytest.approx(38 / 130)
    assert m["mae_pp"] == pytest.approx(20.)
    assert len(c) == 2


def test_expectation_publication_cutoff_and_identity():
    reviewed = pd.DataFrame([{"vote_key": "1", "vote_date": "2021-01-03",
        "wave": 2, "expected_yes_pp": 51., "source_url": "https://example.org/poll",
        "section": "vote"}])
    national = reviewed.drop(columns=["expected_yes_pp", "section"]).assign(
        published_at="2020-12-22T06:00:00Z", survey_midpoint="2020-12-15")
    assert len(validate_expectations(reviewed, national)) == 1
    with pytest.raises(ValueError):
        validate_expectations(reviewed, national.assign(published_at="2021-01-03T06:00:00Z"))
    with pytest.raises(ValueError):
        validate_expectations(reviewed.assign(source_url="https://example.org/other"), national)

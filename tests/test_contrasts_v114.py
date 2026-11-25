import pandas as pd
import pytest

from scripts.modeling.contrasts_v114 import CONFIGS, centered_error, choose_config, inner_windows


def test_centered_error_removes_only_object_offset():
    actual = [0., .2, .4, .6]
    votes = ["a", "a", "b", "b"]
    assert centered_error(actual, [.1, .3, .2, .4], votes) == pytest.approx(0.)
    assert centered_error(actual, [.1, .1, .5, .7], votes) == pytest.approx(5.)


def test_equal_object_weight():
    assert centered_error([0., 0., 0., 0., 0., 0.],
                          [-.1, .1, 0., 0., 0., 0.],
                          ["a", "a", "b", "b", "b", "b"]) == pytest.approx(5.)


def test_date_blocks_disjoint():
    dates = pd.date_range("2000-01-01", periods=40, freq="90D")
    train = pd.DataFrame({"vote_date": dates.repeat(2)})
    a, b = inner_windows(train)
    assert a == (dates[24], dates[32])
    assert b == (dates[32], None)


def test_selection_and_ties():
    scores = {name: [1., 1.] for name in CONFIGS}
    assert choose_config(scores) == "rank5_alpha100"
    scores["rank20_alpha10"] = [.5, .9]
    assert choose_config(scores) == "rank20_alpha10"
    del scores["rank5_alpha10"]
    with pytest.raises(ValueError):
        choose_config(scores)

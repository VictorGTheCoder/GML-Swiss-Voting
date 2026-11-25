import pandas as pd
import pytest

from scripts.modeling.rolling_v116 import date_windows, split_date


def test_grouped_dates_and_strict_history():
    data = pd.DataFrame({"vote_date": pd.to_datetime(["2019-01-01", "2020-01-01", "2020-01-01", "2021-01-01"])})
    windows = date_windows(data.vote_date)
    assert len(windows) == 3
    train, valid = split_date(data, windows[1]["start"])
    assert len(train) == 1 and len(valid) == 2
    assert train.vote_date.max() < valid.vote_date.min()


def test_forbidden_date():
    with pytest.raises(ValueError):
        date_windows(["2023-01-01"])

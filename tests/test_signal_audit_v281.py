import pandas as pd
import pytest

from scripts.modeling.signal_audit_v281 import bucket, latest, paired_interval


def test_age_buckets():
    assert [bucket(x) for x in [1, 14, 15, 30, 31, float("nan")]] == [
        "0-14", "0-14", "15-30", "15-30", ">30", "absent_or_undated"
    ]
    with pytest.raises(ValueError):
        bucket(0)


def test_latest_and_strict_date():
    roster = pd.DataFrame({"vote_key": ["a"], "vote_date": ["2022-09-25"]})
    source = pd.DataFrame({
        "vote_key": ["a", "a"], "vote_date": ["2022-09-25"] * 2,
        "published": ["2022-08-01", "2022-09-15"],
    })
    assert latest(source, roster, "published").loc["a"] == 10
    source.loc[1, "published"] = "2022-09-25"
    with pytest.raises(ValueError):
        latest(source, roster, "published")


def test_wrong_identity():
    roster = pd.DataFrame({"vote_key": ["a"], "vote_date": ["2022-09-25"]})
    source = pd.DataFrame({
        "vote_key": ["a"], "vote_date": ["2022-09-24"], "published": ["2022-09-15"]
    })
    with pytest.raises(ValueError):
        latest(source, roster, "published")


def test_bootstrap_dates():
    g = pd.DataFrame({"vote_date": ["a", "a", "b"], "gain_national": [2., 2., 2.]})
    assert paired_interval(g) == [2., 2.]
    assert paired_interval(g.iloc[:2]) is None

import pandas as pd
import pytest

from scripts.modeling.media_v102 import correction, validate_media


def sample():
    return pd.DataFrame({
        "vote_key": ["a", "b", "c"], "vote_date": ["2022-01-09"] * 3,
        "published_at": ["2022-01-01"] * 3, "weeks": [9] * 3,
        "report_label": ["joint", "joint", "other"], "articles": [100, 100, 50],
        "tone": [20, 20, -10], "source_url": ["https://www.foeg.uzh.ch/a"] * 3,
    })


def test_combined_volume():
    result = validate_media(sample())
    assert result.prominence.tolist() == pytest.approx([2/3, 2/3, 1/3])


def test_same_date_publication_rejected():
    d = sample()
    d["published_at"] = d.vote_date
    with pytest.raises(ValueError, match="too late"):
        validate_media(d)


def test_same_date_not_used():
    row = next(validate_media(sample()).itertuples())
    day = pd.Timestamp("2022-01-09")
    history = [(day, row, 1.)] * 10
    assert correction(history, row, "tone", day) == 0.


def test_prior_dates_only_and_fallback():
    row = next(validate_media(sample()).itertuples())
    day = pd.Timestamp("2022-01-09")
    past = [(day - pd.Timedelta(days=i), row, .2) for i in range(1, 8)]
    assert 0 < correction(past, row, "tone", day) <= .10
    assert correction(past, None, "tone", day) == 0.

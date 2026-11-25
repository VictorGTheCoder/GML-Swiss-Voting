import numpy as np
import pandas as pd
import pytest

from scripts.modeling.geographic_budget_v135 import geographic_diagnosis, match_scoring_geography


def test_canton_offsets_remove_between_error():
    result = geographic_diagnosis([.2, .3, .4, .5], [.3, .4, .3, .4], ["A", "A", "B", "B"])
    assert result["canton_offset_oracle_pp"] == pytest.approx(0, abs=1e-9)
    assert result["canton_offset_gain_pp"] == pytest.approx(10)
    assert result["between_canton_pp2"] == pytest.approx(100)
    assert result["within_canton_pp2"] == pytest.approx(0, abs=1e-9)


def test_within_canton_cannot_be_removed():
    result = geographic_diagnosis([.2, .3, .4, .5], [.3, .2, .5, .4], ["A", "A", "B", "B"])
    assert result["canton_offset_oracle_pp"] == pytest.approx(10)
    assert result["between_canton_pp2"] == pytest.approx(0, abs=1e-9)
    assert result["within_canton_pp2"] == pytest.approx(100)


def test_unequal_groups_and_l2_identity():
    rng = np.random.default_rng(135)
    y, p = rng.uniform(0, 1, (2, 13))
    result = geographic_diagnosis(y, p, ["A"] * 2 + ["B"] * 11)
    assert result["mse_pp2"] == pytest.approx(
        sum(result[k] for k in ("global_bias_pp2", "between_canton_pp2", "within_canton_pp2")))
    assert result["canton_offset_oracle_pp"] <= result["median_offset_oracle_pp"] + 1e-8
    assert "predictions" not in result


def test_invalid_geography():
    with pytest.raises(ValueError):
        geographic_diagnosis([.1], [.2], [None])


def test_exact_scoring_join():
    frame = pd.DataFrame({"vote_id": ["a"], "municipality_id": ["1"],
                          "vote_date": pd.to_datetime(["2022-01-01"]), "yes_share": [.4]})
    actual = frame.drop(columns="yes_share").assign(canton="A", votes_yes=4, votes_no=6)
    assert len(match_scoring_geography(frame, actual)) == 1
    with pytest.raises(ValueError):
        match_scoring_geography(frame, actual.assign(votes_yes=5))
    with pytest.raises(ValueError):
        match_scoring_geography(frame, actual.assign(vote_date=pd.Timestamp("2023-01-01")))
    with pytest.raises(ValueError):
        match_scoring_geography(frame, actual.assign(municipality_id="2"))
    with pytest.raises(ValueError):
        match_scoring_geography(frame, pd.concat([actual, actual]))

import pandas as pd
import pytest

from scripts.integration.build_modeling_dataset import (
    DEMOGRAPHICS,
    FLAGS,
    asof_join,
    build,
    election_wide,
    prior_history,
)


def test_history_excludes_all_same_day_objects_and_future_outcomes():
    frame = pd.DataFrame({
        "municipality_id": ["0001"] * 4 + ["0002"],
        "vote_date": pd.to_datetime(["2010-01-01", "2011-01-01", "2011-01-01", "2012-01-01", "2012-01-01"]),
        "yes_share": [.2, .6, 1., .9, .5],
    })
    history = prior_history(frame).set_index(["municipality_id", "vote_date"])
    assert history.loc[("0001", "2011-01-01"), "history_mean_yes"] == pytest.approx(.2)
    assert history.loc[("0001", "2012-01-01"), "history_mean_yes"] == pytest.approx(.6)
    assert history.loc[("0001", "2012-01-01"), "history_n_objects"] == 3
    assert pd.isna(history.loc[("0002", "2012-01-01"), "history_mean_yes"])
    pd.testing.assert_frame_equal(prior_history(frame), prior_history(frame.sample(frac=1, random_state=3)))


def test_asof_preserves_order_and_respects_release_boundary():
    left = pd.DataFrame({"municipality_id": ["0001"] * 3, "vote_id": ["a", "b", "c"],
                         "feature_cutoff": pd.to_datetime(["2020-09-02", "2019-01-01", "2020-09-01"])})
    right = pd.DataFrame({"municipality_id": pd.Series(["0001", "0001"], dtype="string"),
                          "available": pd.to_datetime(["2019-09-02", "2020-09-02"]), "value": [10, 20]})
    result = asof_join(left, right, "available")
    assert result.vote_id.tolist() == ["a", "b", "c"]
    assert result.value.iloc[0] == 20
    assert pd.isna(result.value.iloc[1])
    assert result.value.iloc[2] == 10
    with pytest.raises(ValueError, match="duplicate keys"):
        asof_join(left, pd.concat([right, right.iloc[:1]]), "available")


def test_elections_keep_zero_and_missing_distinct_and_exclude_current_year():
    elections = pd.DataFrame({"municipality_id": ["0001"] * 3, "election_year": [2019, 2019, 2023],
                             "party_code": ["1", "3", "1"], "party_share": [0., None, .9], "is_special_unit": False})
    left = pd.DataFrame({"municipality_id": ["0001"], "feature_cutoff": pd.to_datetime(["2023-12-30"])})
    joined = asof_join(left, election_wide(elections), "election_selection_from")
    assert joined.election_year.iloc[0] == 2019
    assert joined.party_share_plr.iloc[0] == 0
    assert pd.isna(joined.party_share_ps.iloc[0])


def test_build_filters_outcomes_and_keeps_one_row_without_source_mutation():
    dates = pd.to_datetime(["2011-03-01", "2012-03-01", "2013-03-01", "2014-03-01"])
    ofs = pd.DataFrame({"municipality_id": ["0001"] * 4, "vote_id": ["10", "20", "30", "40"],
                        "vote_key": ["10", "20", "30", "40"], "vote_date": dates, "canton": "VD",
                        "votes_yes": [20, 60, 80, 99], "votes_no": [80, 40, 20, 1], **dict.fromkeys(FLAGS, False)})
    ofs.loc[3, "is_provisional"] = True
    swiss = pd.DataFrame({"vote_key": ["10", "20", "30", "40"], "swissvotes_id": ["1", "2", "3", "4"],
                          "vote_date": dates, "is_tiebreak_question": False, "rechtsform": 1,
                          "d1e1": "1", "d2e1": None, "d3e1": None})
    statpop = pd.DataFrame({"municipality_id": ["0001"], "year": [2010],
                           "available_from": pd.to_datetime(["2011-09-02"]), **dict.fromkeys(DEMOGRAPHICS, 0.5)})
    elections = pd.DataFrame({"municipality_id": ["0001"], "election_year": [2011], "party_code": ["1"],
                             "party_share": [.3], "is_special_unit": False})
    typologies = pd.DataFrame({"municipality_id": ["0001"], "urban_rural": ["1"], "language_region": ["2"]})
    sources = {"ofs": ofs, "swissvotes": swiss, "statpop": statpop, "elections": elections, "typologies": typologies}
    originals = {key: value.copy(deep=True) for key, value in sources.items()}
    table, report = build(sources)
    assert table.vote_id.tolist() == ["20", "30"]
    assert table.history_mean_yes.tolist() == pytest.approx([.2, .4])
    assert table.yes_share.tolist() == pytest.approx([.6, .8])
    assert report["join_row_losses"] == 0
    assert not table.strict_forecast_ready.any()
    assert "yes_share" not in report["numeric_features"]
    assert "votes_yes" not in table
    for name, value in sources.items():
        pd.testing.assert_frame_equal(value, originals[name])

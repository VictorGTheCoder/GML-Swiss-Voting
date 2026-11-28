from datetime import date

import pytest

from scripts.modeling.poll_source_audit_v132 import audit


def test_candidates_fail_closed_and_do_not_compare_early_wave():
    vote = date(2018, 3, 4)
    row = {"vote_key": "6170", "vote_date": vote.isoformat(), "wave": "1",
           "fieldwork_start": "2018-01-15", "fieldwork_end": "2018-01-15",
           "stated_release_date": "2018-01-19", "yes_share_pp": "40",
           "comparison_role": "early_wave"}
    result = audit([row], {"6170": 39}, {"6170": vote})
    assert result["early_waves"] == 1
    assert result["latest_candidates"] == 0
    assert result["training_rows_admitted"] == 0
    with pytest.raises(ValueError):
        audit([row, row], {"6170": 39}, {"6170": vote})
    with pytest.raises(ValueError):
        audit([{**row, "stated_release_date": vote.isoformat()}],
              {"6170": 39}, {"6170": vote})


def test_latest_agreement():
    vote = date(2018, 11, 25)
    row = {"vote_key": "6230", "vote_date": vote.isoformat(), "wave": "3",
           "fieldwork_start": "2018-11-08", "fieldwork_end": "2018-11-09",
           "stated_release_date": "2018-11-14", "yes_share_pp": "45",
           "comparison_role": "latest_candidate"}
    result = audit([row], {"6230": 45}, {"6230": vote})
    assert result["latest_candidates"] == result["latest_agreements"] == 1
    assert result["strict_forecast_ready"] is False


def test_multiple_waves_require_chronological_order():
    vote = date(2022, 2, 13)
    first = {"vote_key": "6510", "vote_date": vote.isoformat(), "wave": "1",
             "fieldwork_start": "2022-01-03", "fieldwork_end": "2022-01-04",
             "stated_release_date": "2022-01-07", "yes_share_pp": "34",
             "comparison_role": "early_wave"}
    third = {**first, "wave": "3", "fieldwork_start": "2022-01-27",
             "fieldwork_end": "2022-01-28", "stated_release_date": "2022-02-02",
             "yes_share_pp": "18", "comparison_role": "latest_candidate"}
    result = audit([third, first], {"6510": 18}, {"6510": vote})
    assert result["rows"] == 2
    assert result["multiwave_objects"] == result["multiwave_dates"] == 1
    assert result["latest_agreements"] == 1
    with pytest.raises(ValueError, match="Overlapping or reversed"):
        audit([first, {**third, "fieldwork_start": "2022-01-03"}],
              {"6510": 18}, {"6510": vote})
    with pytest.raises(ValueError, match="Overlapping or reversed"):
        audit([{**first, "stated_release_date": "2022-02-03"}, third],
              {"6510": 18}, {"6510": vote})

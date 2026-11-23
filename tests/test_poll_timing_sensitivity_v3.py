import numpy as np
import pandas as pd
import pytest

from scripts.modeling.poll_timing_sensitivity_v3 import scenario_polls, strict_flags, validate_windows


def poll_rows():
    return pd.DataFrame({
        "vote_key": ["a", "a", "b"], "wave": [1, 2, 1],
        "survey_midpoint_is_approximate": ["True", "True", "False"],
        "survey_midpoint": ["2020-01-05", "2020-02-05", "2020-01-05"],
        "survey_midpoint_lower": ["2020-01-01", "2020-02-01", "2020-01-05"],
        "survey_midpoint_upper": ["2020-01-09", "2020-02-09", "2020-01-05"],
        "survey_start": ["2020-01-01", "2020-02-01", "2020-01-01"],
        "survey_end": ["2020-01-09", "2020-02-09", "2020-01-09"],
        "published_at": ["2020-01-15", "2020-02-15", "2020-01-15"],
        "yes_total": [60., 50., 60.], "no_total": [30., 40., 30.], "undecided": [10.] * 3,
    })


def test_boolean_false_is_false_and_unknown_literals_are_rejected():
    assert strict_flags(pd.Series([True, False, "True", "False"])).tolist() == [True, False, True, False]
    for invalid in ["yes", "0", "1", "", None, np.nan]:
        with pytest.raises(ValueError, match="True/False"):
            strict_flags(pd.Series([invalid]))


@pytest.mark.parametrize("first,second", [("lower", "lower"), ("lower", "upper"), ("upper", "lower"), ("upper", "upper")])
def test_endpoint_scenarios_change_only_flagged_midpoints(first, second):
    original = poll_rows()
    changed = scenario_polls(original, first, second)
    assert changed.survey_midpoint.tolist() == [original.loc[0, f"survey_midpoint_{first}"],
                                                original.loc[1, f"survey_midpoint_{second}"], "2020-01-05"]
    pd.testing.assert_frame_equal(changed.drop(columns="survey_midpoint"), original.drop(columns="survey_midpoint"))
    assert original.survey_midpoint.tolist() == ["2020-01-05", "2020-02-05", "2020-01-05"]


def test_invalid_bounds_and_unexpected_waves_fail_closed():
    with pytest.raises(ValueError, match="bounds"):
        scenario_polls(poll_rows().assign(survey_midpoint_lower="2019-01-01"), "lower", "upper")
    with pytest.raises(ValueError, match="wave"):
        scenario_polls(poll_rows().assign(wave=3), "lower", "upper")


def test_comparison_dates_are_rejected_before_reading_evaluation_targets():
    with pytest.raises(ValueError, match="1990--2022"):
        validate_windows([{"start": "2022-01-01", "end": "2023-01-01"}])
    with pytest.raises(ValueError, match="disjoint"):
        validate_windows([{"start": "2021-01-01", "end": "2021-12-31"},
                          {"start": "2021-12-31", "end": "2022-12-31"}])

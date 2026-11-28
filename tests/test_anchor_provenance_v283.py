import pandas as pd
import pytest

from scripts.modeling.anchor_provenance_v283 import audit


def fixture():
    roster = pd.DataFrame({"vote_key": ["a", "b"], "vote_date": ["2022-02-13"] * 2})
    national = pd.DataFrame({
        "vote_key": ["a", "a", "c"],
        "vote_date": ["2022-02-13", "2022-02-13", "2023-03-12"],
        "wave": ["1", "2", "1"],
        "published_at": ["2022-01-10", "2022-02-01", "2023-02-01"],
        "survey_midpoint": ["2022-01-05", "2022-01-25", "2023-01-25"],
        "chart_url": ["x", "y", "z"],
        "historical_version_verified": ["false"] * 3,
        "late": ["true", "false", "false"],
        "source": ["direct"] * 3,
    })
    margin = pd.concat([national.iloc[[1]]] * 3, ignore_index=True)
    margin["region"] = ["de", "fr", "it"]
    margin["chart_updated_at"] = "2022-02-15"
    return national, margin, roster


def test_selected_waves_and_late():
    national, margin, roster = fixture()
    report = audit(national, {"language": margin}, roster)
    assert report["national_objects"] == 1
    assert report["national_selected_waves"] == 2
    assert report["national_objects_any_late_chart"] == 1
    assert report["national_objects_latest_late_chart"] == 0
    assert report["structural_fallback_objects"] == 1
    assert report["language"]["objects_latest_late_chart"] == 1


def test_cutoff():
    national, margin, roster = fixture()
    national.loc[1, "published_at"] = "2022-02-13"
    with pytest.raises(ValueError, match="cutoff"):
        audit(national, {"language": margin}, roster)


def test_identity():
    national, margin, roster = fixture()
    margin["chart_url"] = "wrong"
    with pytest.raises(ValueError, match="identity"):
        audit(national, {"language": margin}, roster)


def test_incomplete_margin():
    national, margin, roster = fixture()
    with pytest.raises(ValueError, match="Incomplete"):
        audit(national, {"language": margin.iloc[:2]}, roster)

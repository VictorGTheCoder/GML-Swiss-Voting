"""Encoding, correspondence and target-isolation checks for political features."""

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from scripts.modeling.political_features_v2 import (
    PARTIES,
    PARTY_CODES,
    SOURCE_FIELDS,
    add_political_features,
)


def inputs():
    table = pd.DataFrame({
        "municipality_id": ["100", "200", "100", "200"],
        "vote_id": ["6000", "6000", "6010", "6010"],
        "vote_key": ["6000", "6000", "6010", "6010"],
        "vote_date": pd.to_datetime(["2016-02-28"] * 2 + ["2016-06-05"] * 2),
        "yes_share": [0.1, 0.8, 0.7, 0.2],
        "party_share_plr": [0.4, 0.2, 0.4, 0.2],
        "party_share_ps": [0.3, 0.5, 0.3, 0.5],
        "party_share_udc": [0.2, 0.2, 0.2, 0.2],
        "party_share_pdc": [0.05, 0.01, 0.05, 0.01],
        "party_share_pbd": [0.02, 0.01, 0.02, 0.01],
        "party_share_centre": [np.nan] * 4,
        "strict_forecast_ready": [False] * 4,
    }, index=pd.Index([19, 7, 22, 4], name="original_row"))
    swiss = pd.DataFrame({
        "vote_key": ["6010", "6000"],
        "vote_date": ["2016-06-05", "2016-02-28"],
        "rechtsform": ["3", "2"],
        "p-fdp": ["2", "1"], "p-sps": ["1", "2"], "p-svp": ["5", "3"],
        "p-cvp": ["9999", "1"], "p-bdp": ["9999", "2"], "p-mitte": ["1", "9999"],
        "br-pos": ["2", "1"], "bv-pos": ["2", "1"],
        "nr-pos": ["2", "1"], "sr-pos": ["3", "1"],
        "nrja": ["30", "120"], "nrnein": ["170", "60"],
        "srja": ["0", "40"], "srnein": ["0", "4"],
        "ja-lager": ["25", "70"], "nein-lager": ["65", "25"],
        "d1e2": ["10.2", "9.1"], "d1e3": ["10.24", "9.11"],
    })
    return table, swiss


def test_correspondence_original_values_and_expected_interactions():
    table, swiss = inputs()
    original_table, original_source = table.copy(deep=True), swiss.copy(deep=True)
    result, manifest = add_political_features(table, swiss)
    assert_frame_equal(result[table.columns], table)
    assert_frame_equal(table, original_table)
    assert_frame_equal(swiss, original_source)
    assert result.index.equals(table.index)
    assert result.political_recommendation_plr.tolist() == ["yes", "yes", "no", "no"]
    np.testing.assert_allclose(result.political_local_cue_plr, [0.4, 0.2, -0.4, -0.2])
    np.testing.assert_allclose(result.political_local_cue_ps, [-0.3, -0.5, 0.3, 0.5])
    assert result.political_local_cue_udc.isna().all()
    np.testing.assert_allclose(result.political_local_yes_mass, [0.45, 0.21, 0.3, 0.5])
    np.testing.assert_allclose(result.political_local_no_mass, [0.32, 0.51, 0.4, 0.2])
    np.testing.assert_allclose(result.political_nr_yes_fraction, [2 / 3, 2 / 3, 0.15, 0.15])
    np.testing.assert_allclose(result.political_sr_yes_fraction.iloc[:2], [40 / 44] * 2)
    assert result.political_sr_yes_fraction.iloc[2:].isna().all()
    np.testing.assert_allclose(result.political_national_yes_electoral_share, [0.7, 0.7, 0.25, 0.25])
    assert manifest["join"]["matched_rows"] == 4
    assert manifest["mode"] == "exploratory_retrospective"
    assert not manifest["strict_forecast_ready"]
    assert manifest["availability_status"] == "historically_unverified"


def test_all_party_categories_remain_distinct_without_false_neutral_directions():
    codes = list(PARTY_CODES) + [".", "surprise", "1.5"]
    n = len(codes)
    table = pd.DataFrame({"municipality_id": ["100"] * n,
                          "vote_id": [str(6000 + i) for i in range(n)],
                          "vote_key": [str(6000 + i) for i in range(n)],
                          "vote_date": pd.date_range("2010-01-01", periods=n, freq="90D"),
                          "party_share_plr": [0.4] * n})
    swiss = table[["vote_key", "vote_date"]].assign(**{"p-fdp": codes})
    result, manifest = add_political_features(table, swiss)
    assert result.political_recommendation_plr.iloc[:len(PARTY_CODES)].tolist() == list(PARTY_CODES.values())
    np.testing.assert_allclose(result.political_direction_plr.iloc[:2], [1, -1])
    assert result.political_direction_plr.iloc[2:].isna().all()
    assert result.political_local_cue_plr.iloc[2:].isna().all()
    assert result.political_recommendation_plr.iloc[-3:].isna().all()
    assert manifest["invalid_source_values_by_field_on_unique_objects"]["p-fdp"] == 2


def test_no_invented_centre_merger_or_zero_when_local_data_are_absent():
    table, swiss = inputs()
    result, manifest = add_political_features(table, swiss)
    # Centre has an explicit yes but no local Centre election share in the input.
    # PDC/PBD predecessor shares cannot silently fill it.
    assert result.political_local_cue_centre.isna().all()
    assert result.political_local_cue_pdc.iloc[2:].isna().all()
    assert result.political_local_cue_pbd.iloc[2:].isna().all()
    assert "no inherited" in manifest["party_merger_policy"]
    empty_local = table.drop(columns=[c for c in table if c.startswith("party_share_")])
    result, _ = add_political_features(empty_local, swiss)
    assert result.political_local_yes_mass.isna().all()
    assert result.political_local_no_mass.isna().all()
    assert result.political_local_yes_fraction_known.isna().all()
    assert result.political_local_missing_party_count.eq(len(PARTIES)).all()


def test_target_and_campaign_fields_cannot_affect_any_added_predictor():
    table, swiss = inputs()
    a, manifest_a = add_political_features(table, swiss)
    toxic = swiss.assign(**{
        "volkja-proz": [1, 99], "bet": [30, 90], "zh-japroz": [5, 95],
        "finanz-ja-tot": [1000000, 9000000], "mediares-tot": [100, 999],
        "inserate-jaanteil": [1, 0], "prediction": [0.01, 0.99],
    })
    other_table = table.assign(yes_share=1 - table.yes_share)
    b, manifest_b = add_political_features(other_table, toxic)
    features = manifest_a["numeric_features"] + manifest_a["categorical_features"]
    assert_frame_equal(a[features], b[features])
    assert manifest_a == manifest_b
    assert set(manifest_a["source_fields"]) == set(SOURCE_FIELDS)
    assert not set(toxic.columns) - set(swiss.columns) & set(manifest_a["source_fields"])


@pytest.mark.parametrize("failure", ["duplicate_source", "duplicate_row", "date_mismatch", "unmatched",
                                      "null_id", "inconsistent_vote", "subsidiary", "existing_output"])
def test_invalid_correspondence_fails_without_silent_row_dropping(failure):
    table, swiss = inputs()
    if failure == "duplicate_source":
        swiss = pd.concat([swiss, swiss.iloc[[0]]])
    elif failure == "duplicate_row":
        table = pd.concat([table, table.iloc[[0]]])
    elif failure == "date_mismatch":
        swiss.loc[0, "vote_date"] = "2016-06-06"
    elif failure == "unmatched":
        swiss = swiss.iloc[:1]
    elif failure == "null_id":
        table.loc[19, "municipality_id"] = None
    elif failure == "inconsistent_vote":
        table.loc[7, "vote_key"] = "6010"
    elif failure == "subsidiary":
        swiss.loc[0, "rechtsform"] = "5"
    elif failure == "existing_output":
        table["political_direction_plr"] = 1
    with pytest.raises(ValueError):
        add_political_features(table, swiss)


def test_invalid_numerics_become_missing_and_are_audited():
    table, swiss = inputs()
    table.loc[19, "party_share_plr"] = 40  # accidental percentage, not fraction
    swiss.loc[0, "nrja"] = "9999"
    swiss.loc[1, "srja"] = "2.5"
    swiss.loc[0, "ja-lager"] = "130"
    swiss.loc[1, "ja-lager"] = "80"
    swiss.loc[1, "nein-lager"] = "30"
    result, manifest = add_political_features(table, swiss)
    assert pd.isna(result.loc[19, "political_local_cue_plr"])
    assert result.political_nr_yes_fraction.iloc[2:].isna().all()
    assert result.political_sr_yes_fraction.isna().all()
    assert result.political_national_yes_electoral_share.isna().all()
    assert manifest["invalid_local_values_by_field_on_rows"]["party_share_plr"] == 1
    assert manifest["invalid_source_values_by_field_on_unique_objects"]["nr_vote_pair"] == 1
    assert manifest["invalid_source_values_by_field_on_unique_objects"]["national_support_sum_over_one"] == 1


def test_schema_has_unique_explicit_allowlists_and_supports_duplicate_index_labels():
    table, swiss = inputs()
    table.index = [0, 0, 1, 1]
    result, manifest = add_political_features(table, swiss)
    features = manifest["numeric_features"] + manifest["categorical_features"]
    assert len(features) == len(set(features))
    assert set(features) == set(result.columns) - set(table.columns)
    assert all(name.startswith("political_") for name in features)
    assert not set(manifest["numeric_features"]) & set(manifest["categorical_features"])
    assert set(sum(manifest["feature_groups"].values(), [])) == set(features)
    assert all("local_" not in name for name in manifest["object_numeric_features"])
    assert all("local_" not in name for name in manifest["object_categorical_features"])
    assert_frame_equal(result[table.columns], table)
    assert all(result[name].dtype == np.float32 for name in manifest["numeric_features"])

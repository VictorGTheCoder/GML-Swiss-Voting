import hashlib
import json

import pandas as pd
import pytest

from scripts.integration.modeling_municipal import load_local_municipal_sources, prepare_municipal_table


def _inputs(*, missing_age_bin=False, missing_commune=False):
    nationality = pd.DataFrame([
        {"year": 2012, "code": "0001", "population": 100, "swiss": 80, "foreign": 20},
        {"year": 2012, "code": "0002", "population": 300, "swiss": 210, "foreign": 90},
    ])
    age_rows = []
    selected_counts = {
        "0001": {0: 2, 5: 2, 10: 3, 15: 3, 20: 5, 25: 5, 30: 5, 35: 5,
                 40: 8, 45: 8, 50: 8, 55: 8, 60: 8,
                 65: 10, 70: 5, 75: 5, 80: 4, 85: 3, 90: 2, 95: 1, 100: 0},
        "0002": {0: 5, 5: 5, 10: 10, 15: 10, 20: 15, 25: 15, 30: 15, 35: 15,
                 40: 26, 45: 26, 50: 26, 55: 26, 60: 26,
                 65: 25, 70: 15, 75: 12, 80: 10, 85: 8, 90: 5, 95: 3, 100: 2},
    }
    for code, selected in selected_counts.items():
        for lower in [*range(0, 100, 5), 100]:
            if missing_age_bin and code == "0002" and lower == 15:
                continue
            age_rows.append({"year": 2012, "code": code, "age_from": lower,
                             "population": selected.get(lower, 0)})
    age_classes = pd.DataFrame(age_rows)
    crosswalk = pd.DataFrame([
        {"source_municipality_id": code, "target_municipality_id": "9",
         "mapping_type": "merge", "source_geography_id": "source-2025",
         "target_geography_id": "target-2026", "crosswalk_version": "cw-v1",
         "crosswalk_evidence": "official-fixture-register"}
        for code in ["1", "2"]
    ])
    levels = pd.DataFrame([
        {"BfsCode": "9", "Canton": "Zürich", "STALAN2020": "1", "SPRGEB2020": "1",
         "REGCH": "4", "DEGURB2021": "3"},
    ])
    if missing_commune:
        levels = levels.iloc[:0]
    outcomes = pd.DataFrame([
        {"municipality_id": code, "vote_id": "700", "vote_date": "2012-03-11",
         "votes_yes": 30, "votes_no": 70, "is_special_unit": False,
         "is_tiebreak_question": False, "is_provisional": False}
        for code in ["9", "10"]
    ])
    forecasts = pd.DataFrame([
        {"vote_id": "700", "forecast_at": "2012-03-01T12:00:00Z",
         "forecast_source": "fixture-brochure", "forecast_source_version": "fixture-v1",
         "forecast_evidence": "fixture-publication-record"}
    ])
    return outcomes, forecasts, nationality, age_classes, levels, crosswalk


def _prepare(*, missing_age_bin=False, missing_commune=False):
    outcomes, forecasts, nationality, ages, levels, crosswalk = _inputs(
        missing_age_bin=missing_age_bin, missing_commune=missing_commune
    )
    result = prepare_municipal_table(
        outcomes, forecasts, nationality, ages, levels, crosswalk,
        geography_id="target-2026", source_version="outcomes-v1",
        population_source_version="pop-v1", population_source_url="https://example.test/pop",
        age_source_version="age-v1", age_source_url="https://example.test/age",
        territory_source_version="territory-v1", territory_source_url="https://example.test/territory",
    )
    return result


def test_prepared_table_aggregates_counts_before_shares_and_keeps_nominal_categories():
    result = _prepare()
    row = result.preparation.prepared.query("municipality_id == '9'").iloc[0]

    assert row["statpop_population__population_total"] == 400
    assert row["statpop_population__share_foreign"] == pytest.approx(0.275)
    assert row["statpop_age__share_age_0_19"] == pytest.approx(0.1)
    assert row["statpop_age__share_age_20_39"] == pytest.approx(0.2)
    assert row["statpop_age__share_age_65_plus"] == pytest.approx(0.275)
    assert row["municipal_context__canton"] == "Zürich"
    assert row["municipal_context__urban_rural_type"] == "urban"
    assert row["language_region__language_region"] == "1"
    assert result.preparation.strict_population.municipality_id.tolist() == ["10"]
    assert result.preparation.readiness["strict_population_rows"] == 1
    assert result.audit["language_region"]["source_field"] == "SPRGEB2020"
    assert result.audit["language_region"]["availability_status"] == {"unknown": 1}


def test_unavailable_municipal_source_keeps_commune_row_and_records_missing_values():
    result = _prepare(missing_commune=True)
    rows = result.preparation.prepared.set_index("municipality_id")

    assert set(rows.index) == {"9", "10"}
    assert pd.isna(rows.loc["10", "statpop_population__population_total"])
    report = result.preparation.feature_join_report
    assert set(report.loc[report.municipality_id.eq("10"), "status"]) == {"missing_entity"}
    assert result.audit["missing_territory_records"] == 2


def test_missing_age_group_bin_does_not_become_zero_or_remove_the_commune():
    result = _prepare(missing_age_bin=True)
    row = result.preparation.prepared.query("municipality_id == '9'").iloc[0]

    assert row["statpop_population__population_total"] == 400
    assert pd.isna(row["statpop_age__share_age_0_19"])
    assert row["statpop_age__share_age_20_39"] == pytest.approx(0.2)
    assert row["statpop_age__share_age_65_plus"] == pytest.approx(0.275)


def test_duplicate_source_release_or_geography_mapping_fails_closed():
    outcomes, forecasts, nationality, ages, levels, crosswalk = _inputs()
    nationality = pd.concat([nationality, nationality.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate.*year.*code"):
        prepare_municipal_table(
            outcomes, forecasts, nationality, ages, levels, crosswalk,
            geography_id="target-2026", source_version="outcomes-v1",
            population_source_version="pop-v1", population_source_url="https://example.test/pop",
            age_source_version="age-v1", age_source_url="https://example.test/age",
            territory_source_version="territory-v1", territory_source_url="https://example.test/territory",
        )


def test_publication_proof_cannot_admit_a_different_source_vintage():
    outcomes, forecasts, nationality, ages, levels, crosswalk = _inputs()
    evidence = pd.DataFrame([{"year": 2012, "code": code,
                              "published_at": "2013-08-01", "availability_evidence": "archive"}
                             for code in ["1", "2"]])
    with pytest.raises(ValueError, match="source_version"):
        prepare_municipal_table(
            outcomes, forecasts, nationality, ages, levels, crosswalk,
            geography_id="target-2026", source_version="outcomes-v1",
            population_source_version="pop-v1", population_source_url="fixture:pop",
            age_source_version="age-v1", age_source_url="fixture:age",
            territory_source_version="territory-v1", territory_source_url="fixture:territory",
            population_publication_evidence=evidence,
        )


def test_late_classification_is_retained_but_never_admitted_at_forecast():
    outcomes, forecasts, nationality, ages, levels, crosswalk = _inputs()
    proof = pd.DataFrame([{"municipality_id": "9", "published_at": "2026-10-01",
                           "availability_evidence": "official-release-record",
                           "source_version": "territory-v1"}])
    result = prepare_municipal_table(
        outcomes, forecasts, nationality, ages, levels, crosswalk,
        geography_id="target-2026", source_version="outcomes-v1",
        population_source_version="pop-v1", population_source_url="fixture:pop",
        age_source_version="age-v1", age_source_url="fixture:age",
        territory_source_version="territory-v1", territory_source_url="fixture:territory",
        territory_publication_evidence=proof, language_publication_evidence=proof,
    )
    row = result.preparation.prepared.query("municipality_id == '9'").iloc[0]
    assert row["municipal_context__urban_rural_type"] == "urban"
    report = result.preparation.feature_join_report
    assert report.query("municipality_id == '9' and block_id == 'municipal_context'").status.tolist() == ["unavailable_at_forecast"]
    assert "9" not in result.preparation.strict_population.municipality_id.tolist()


def test_suppressed_population_counts_remain_missing_without_losing_observations():
    outcomes, forecasts, nationality, ages, levels, crosswalk = _inputs()
    nationality["foreign"] = nationality.foreign.astype(object)
    nationality.loc[0, "foreign"] = "..."
    result = prepare_municipal_table(
        outcomes, forecasts, nationality, ages, levels, crosswalk,
        geography_id="target-2026", source_version="outcomes-v1",
        population_source_version="pop-v1", population_source_url="fixture:pop",
        age_source_version="age-v1", age_source_url="fixture:age",
        territory_source_version="territory-v1", territory_source_url="fixture:territory",
    )
    row = result.preparation.prepared.query("municipality_id == '9'").iloc[0]
    assert row["statpop_population__population_total"] == 400
    assert pd.isna(row["statpop_population__share_foreign"])
    assert len(result.preparation.prepared) == 2
    assert result.audit["population"]["invalid_or_missing_foreign_rows"] == 1


@pytest.mark.parametrize("tampered", [
    "features/statpop_nationality.csv", "features/statpop_age_classes.csv",
    "features/commune_levels_2026-01-01.csv", "geography/register_snapshot_2025-04-06.csv",
    "geography/register_snapshot_2026-01-01.csv", "geography/register_mutations_2010_2026.csv",
])
def test_source_loader_rejects_modified_bytes_before_using_vintage_metadata(tmp_path, tampered):
    files = [
        "features/statpop_nationality.csv", "features/statpop_age_classes.csv",
        "features/commune_levels_2026-01-01.csv", "geography/register_snapshot_2025-04-06.csv",
        "geography/register_snapshot_2026-01-01.csv", "geography/register_mutations_2010_2026.csv",
    ]
    original = b"fixture,value\n1,100\n"
    for relative in files:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(original)
        path.with_suffix(".provenance.json").write_text(json.dumps({
            "sha256": hashlib.sha256(original).hexdigest(),
        }))
    (tmp_path / tampered).write_bytes(original + b"2,200\n")
    with pytest.raises(ValueError, match="SHA-256"):
        load_local_municipal_sources(tmp_path)
    assert (tmp_path / tampered).read_bytes() == original + b"2,200\n"

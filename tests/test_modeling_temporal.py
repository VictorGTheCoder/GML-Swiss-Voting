import pandas as pd

from scripts.integration.prepare_modeling import prepare_base_table
from scripts.integration.modeling_temporal import (
    attach_temporal_evidence,
    prepare_modeling_table,
    select_evidenced_publication,
)
from scripts.feature_blocks import FeatureBlock


def outcomes():
    return pd.DataFrame([
        {"municipality_id": "0001", "vote_id": "100", "vote_date": "2020-09-27",
         "votes_yes": 25, "votes_no": 75, "is_special_unit": False,
         "is_tiebreak_question": False, "is_provisional": False},
        {"municipality_id": "0001", "vote_id": "110", "vote_date": "2021-11-28",
         "votes_yes": 40, "votes_no": 60, "is_special_unit": False,
         "is_tiebreak_question": False, "is_provisional": False},
        {"municipality_id": "0002", "vote_id": "110", "vote_date": "2021-11-28",
         "votes_yes": 0, "votes_no": 100, "is_special_unit": False,
         "is_tiebreak_question": False, "is_provisional": False},
    ])


def forecast_provenance(frame):
    frame["forecast_source"] = "fixture brochure archive"
    frame["forecast_source_version"] = "fixture-brochures-v1"
    return frame


def result_provenance(frame):
    frame["result_source"] = "fixture BFS results"
    frame["result_source_version"] = "fixture-results-v1"
    return frame


def test_forecast_and_result_publication_evidence_are_attached_by_object_without_fabrication():
    base = prepare_base_table(outcomes(), geography_id="bfs-2026-01-01", source_version="ofs-v1")
    forecasts = pd.DataFrame([
        {"vote_id": "100", "forecast_at": "2020-09-17T10:00:00Z", "forecast_evidence": "brochure-100"},
        {"vote_id": "110", "forecast_at": "2021-11-18T10:00:00Z", "forecast_evidence": "brochure-110"},
    ])
    forecasts = forecast_provenance(forecasts)
    results = pd.DataFrame([
        {"vote_id": "100", "result_available_at": "2020-09-28T08:00:00Z",
         "result_availability_evidence": "bfs-results-100"},
    ])
    results = result_provenance(results)

    prepared = attach_temporal_evidence(base.prepared, forecasts, results)

    assert prepared.loc[prepared.vote_id.eq("100"), "forecast_at"].nunique() == 1
    assert prepared.loc[prepared.vote_id.eq("100"), "result_available_at"].notna().all()
    assert prepared.loc[prepared.vote_id.eq("110"), "result_available_at"].isna().all()
    assert prepared.loc[prepared.vote_id.eq("110"), "result_availability_status"].eq("unknown").all()
    assert prepared.loc[prepared.vote_id.eq("110"), "forecast_at"].eq(pd.Timestamp("2021-11-18T10:00Z")).all()


def test_strict_population_requires_forecast_evidence_but_not_target_result_before_its_forecast():
    forecasts = pd.DataFrame([
        {"vote_id": "100", "forecast_at": "2020-09-17T10:00:00Z", "forecast_evidence": "brochure-100"},
        {"vote_id": "110", "forecast_at": "2021-11-18T10:00:00Z", "forecast_evidence": "brochure-110"},
    ])
    forecasts = forecast_provenance(forecasts)
    # Vote 110's result is deliberately published after voting; it is its target,
    # not a predictor required at the forecast instant.
    results = pd.DataFrame([
        {"vote_id": "100", "result_available_at": "2020-09-28T08:00:00Z",
         "result_availability_evidence": "bfs-results-100"},
        {"vote_id": "110", "result_available_at": "2021-11-29T08:00:00Z",
         "result_availability_evidence": "bfs-results-110"},
    ])
    results = result_provenance(results)

    result = prepare_modeling_table(
        outcomes(), geography_id="bfs-2026-01-01", source_version="ofs-v1",
        forecast_publications=forecasts, result_publications=results,
    )

    assert len(result.prepared) == 3
    assert len(result.strict_population) == 3
    assert result.strict_population.loc[result.strict_population.vote_id.eq("110"), "target_share"].tolist() == [.4, .0]
    assert result.strict_population.loc[result.strict_population.vote_id.eq("110"), "result_available_at"].gt(
        result.strict_population.loc[result.strict_population.vote_id.eq("110"), "forecast_at"]
    ).all()


def test_missing_and_late_forecast_evidence_stays_prepared_and_is_reported_by_key():
    forecasts = pd.DataFrame([
        {"vote_id": "100", "forecast_at": "2020-09-28T08:00:00Z", "forecast_evidence": "late-brochure"},
    ])
    forecasts = forecast_provenance(forecasts)
    result = prepare_modeling_table(
        outcomes(), geography_id="bfs-2026-01-01", source_version="ofs-v1",
        forecast_publications=forecasts,
    )

    assert len(result.prepared) == 3
    assert result.strict_population.empty
    statuses = result.prepared.groupby("vote_id").forecast_status.unique().to_dict()
    assert statuses["100"].tolist() == ["forecast_not_before_vote"]
    assert statuses["110"].tolist() == ["unknown"]
    reasons = set(result.exclusions.reason)
    assert reasons == {"forecast_not_before_vote", "forecast_evidence_missing"}
    assert set(result.exclusions.loc[result.exclusions.reason.eq("forecast_evidence_missing"), "vote_id"]) == {"110"}
    assert result.readiness["strict_population_rows"] == 0


def test_unknown_duplicate_or_conflicting_publication_records_fail_closed():
    bad = pd.DataFrame([
        {"vote_id": "100", "forecast_at": "2020-09-17", "forecast_evidence": "a"},
        {"vote_id": "100", "forecast_at": "2020-09-18", "forecast_evidence": "b"},
    ])
    bad = forecast_provenance(bad)
    base = prepare_base_table(outcomes(), geography_id="bfs-2026-01-01", source_version="ofs-v1")

    try:
        attach_temporal_evidence(base.prepared, bad)
    except ValueError as error:
        assert "duplicate" in str(error).lower() or "conflict" in str(error).lower()
    else:
        raise AssertionError("conflicting publication times must not pick a row")


def test_latest_feature_version_requires_publication_and_reference_both_before_forecast():
    records = pd.DataFrame([
        {"entity_id": "a", "reference_date": "2019-12-31", "published_at": "2020-01-02",
         "availability_status": "verified", "availability_evidence": "archive-1", "source_version": "v1", "value": 10},
        {"entity_id": "a", "reference_date": "2020-01-01", "published_at": "2020-01-04",
         "availability_status": "verified", "availability_evidence": "archive-2", "source_version": "v2", "value": 20},
        {"entity_id": "a", "reference_date": "2020-01-10", "published_at": "2020-01-03",
         "availability_status": "verified", "availability_evidence": "archive-future-ref", "source_version": "v3", "value": 30},
        {"entity_id": "a", "reference_date": "2019-12-31", "published_at": None,
         "availability_status": "unknown", "availability_evidence": None, "source_version": "current-only", "value": 99},
    ])
    observations = pd.DataFrame([
        {"entity_id": "a", "forecast_at": "2020-01-05"},
        {"entity_id": "missing", "forecast_at": "2020-01-05"},
    ])

    selected = select_evidenced_publication(records, observations, entity="entity_id", value_columns=("value",))

    assert selected.loc[0, "value"] == 20
    assert selected.loc[0, "source_version"] == "v2"
    assert selected.loc[0, "availability_evidence"] == "archive-2"
    assert selected.loc[0, "selection_status"] == "matched"
    assert selected.loc[1, "selection_status"] == "missing_entity"


def test_feature_published_after_brochure_but_before_vote_is_not_selected_or_strictly_eligible():
    forecast = pd.DataFrame([
        {"vote_id": "100", "forecast_at": "2020-09-17T10:00:00Z", "forecast_evidence": "brochure-100"},
        {"vote_id": "110", "forecast_at": "2021-11-18T10:00:00Z", "forecast_evidence": "brochure-110"},
    ])
    forecast = forecast_provenance(forecast)
    block = FeatureBlock(
        block_id="municipal_test", scope="municipality",
        records=pd.DataFrame([
            {"municipality_id": "1", "geography_id": "bfs-2026-01-01", "reference_date": "2020-08-31",
             "published_at": "2020-09-20", "availability_status": "verified",
             "availability_evidence": "publication-after-brochure", "source_version": "test-v1", "population": 100},
        ]),
        numeric_features=("population",), categorical_features=(), definitions={"population": "fixture population"},
        source_url="https://example.test/source", source_version="test-v1", geography_mode="retrospective_fixed",
    )

    result = prepare_modeling_table(
        outcomes(), geography_id="bfs-2026-01-01", source_version="ofs-v1",
        forecast_publications=forecast, feature_blocks=(block,),
    )

    assert len(result.prepared) == 3
    selected = result.prepared.set_index(["municipality_id", "vote_id"])
    # Full preparation retains the value for inspection, with its unknown-time
    # status and source evidence attached; strict eligibility remains gated.
    assert selected.loc[("1", "100"), "municipal_test__population"] == 100
    assert selected.loc[("1", "100"), "municipal_test__availability_status"] == "unavailable_at_forecast"
    assert selected.loc[("1", "100"), "municipal_test__availability_evidence"] == "publication-after-brochure"
    assert selected.loc[("1", "110"), "municipal_test__population"] == 100
    assert pd.isna(selected.loc[("2", "110"), "municipal_test__population"])
    assert set(result.feature_join_report.status) == {"unavailable_at_forecast", "missing_entity", "matched"}
    assert len(result.strict_population) == 2
    assert "2" in set(result.strict_population.municipality_id)
    assert "feature_unavailable_at_forecast" in set(result.exclusions.reason)


def test_complete_table_is_accepted_by_existing_evaluation_orchestrator():
    data = pd.concat([outcomes(), pd.DataFrame([
        {"municipality_id": "0001", "vote_id": "120", "vote_date": "2022-09-25",
         "votes_yes": 50, "votes_no": 50, "is_special_unit": False,
         "is_tiebreak_question": False, "is_provisional": False},
    ])], ignore_index=True)
    forecasts = pd.DataFrame([
        {"vote_id": vote, "forecast_at": forecast, "forecast_evidence": f"brochure-{vote}"}
        for vote, forecast in [("100", "2020-09-17"), ("110", "2021-11-18"), ("120", "2022-09-15")]
    ])
    forecasts = forecast_provenance(forecasts)
    results = pd.DataFrame([
        {"vote_id": vote, "result_available_at": available, "result_availability_evidence": f"result-{vote}"}
        for vote, available in [("100", "2020-09-28"), ("110", "2021-11-29"), ("120", "2022-09-26")]
    ])
    results = result_provenance(results)
    prepared = prepare_modeling_table(
        data, geography_id="bfs-2026-01-01", source_version="ofs-v1",
        forecast_publications=forecasts, result_publications=results,
    )

    from scripts.evaluate_votes import EvaluationConfig, evaluate

    config = EvaluationConfig(("2020-09-27",), ("2021-11-28",), ("2022-09-25",))
    evaluation = evaluate(prepared.strict_population, config)

    assert len(evaluation["eligible_rows"]) == 4
    assert set(evaluation["eligible_rows"].partition) == {"train", "validation", "test"}


def test_unknown_forecast_keeps_retrospective_feature_value_and_audit_row():
    source = outcomes().loc[lambda frame: frame.vote_id.eq("100")].copy()
    block = FeatureBlock(
        block_id="municipal_test", scope="municipality",
        records=pd.DataFrame([{
            "municipality_id": "1", "geography_id": "bfs-2026-01-01",
            "reference_date": "2020-08-31", "published_at": "2020-09-20",
            "availability_status": "unknown", "availability_evidence": "archive-check-pending",
            "source_version": "test-v1", "population": 321,
        }]),
        numeric_features=("population",), categorical_features=(),
        definitions={"population": "fixture population"},
        source_url="https://example.test/source", source_version="test-v1",
        geography_mode="retrospective_fixed",
    )

    result = prepare_modeling_table(
        source, geography_id="bfs-2026-01-01", source_version="ofs-v1",
        forecast_publications=None, feature_blocks=(block,),
    )

    row = result.prepared.iloc[0]
    assert pd.isna(row.forecast_at)
    assert row.municipal_test__population == 321
    assert row.municipal_test__availability_status == "unknown_availability"
    assert row.municipal_test__source_version == "test-v1"
    assert row.municipal_test__availability_evidence == "archive-check-pending"
    assert len(result.feature_join_report) == 1
    assert result.feature_join_report.iloc[0].status == "unknown_availability"
    assert result.strict_population.empty
    assert "feature_unknown_availability" in set(result.exclusions.reason)


def test_historically_existing_geography_requires_mapping_available_and_valid_at_forecast():
    source = outcomes().loc[lambda frame: frame.vote_id.eq("100")].copy()
    crosswalk = pd.DataFrame([
        {"source_municipality_id": "1", "target_municipality_id": "1", "mapping_type": "identity",
         "source_geography_id": "ofs-2010", "target_geography_id": "bfs-2026-01-01",
         "crosswalk_version": "cw-v1", "crosswalk_evidence": "register-mutation-record",
         "mapping_available_at": "2020-09-18", "target_valid_from": "2020-01-01",
         "target_valid_to": "2021-01-01"},
    ])
    forecast = pd.DataFrame([
        {"vote_id": "100", "forecast_at": "2020-09-17", "forecast_evidence": "brochure-100"},
    ])
    forecast = forecast_provenance(forecast)

    result = prepare_modeling_table(
        source, geography_id="bfs-2026-01-01", source_geography_id="ofs-2010",
        source_version="ofs-v1", geography_crosswalk=crosswalk,
        forecast_publications=forecast, geography_mode="historically_existing",
    )

    assert len(result.prepared) == 1
    assert result.prepared.geography_status.item() == "unavailable_or_not_valid_at_forecast"
    assert result.strict_population.empty
    assert "geography_unavailable_at_forecast" in set(result.exclusions.reason)

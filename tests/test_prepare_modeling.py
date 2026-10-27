import pandas as pd
from scripts.evaluate_votes import REQUIRED

from scripts.integration.prepare_modeling import prepare_base_table


def test_base_table_keeps_object_identity_targets_and_audit_rows():
    outcomes = pd.DataFrame([
        {"municipality_id": "001", "vote_id": "10", "vote_date": "2012-03-11",
         "votes_yes": 30, "votes_no": 70, "is_special_unit": False,
         "is_tiebreak_question": False, "is_provisional": False},
        {"municipality_id": "001", "vote_id": "11", "vote_date": "2012-03-11",
         "votes_yes": 75, "votes_no": 25, "is_special_unit": False,
         "is_tiebreak_question": True, "is_provisional": False},
        {"municipality_id": "002", "vote_id": "12", "vote_date": "2026-01-01",
         "votes_yes": 0, "votes_no": 0, "is_special_unit": False,
         "is_tiebreak_question": False, "is_provisional": False},
        {"municipality_id": "9001", "vote_id": "12", "vote_date": "2026-01-01",
         "votes_yes": 10, "votes_no": 10, "is_special_unit": True,
         "is_tiebreak_question": False, "is_provisional": False},
    ])

    result = prepare_base_table(outcomes, geography_id="bfs-2026", source_version="fixture-v1")

    table = result.prepared
    assert len(table) == 4
    assert table.loc[table.vote_id.eq("10"), "target_share"].item() == 0.3
    assert table.loc[table.vote_id.eq("11"), "target_share"].item() == 0.75
    assert table.vote_id.astype(str).str.fullmatch(r"\d+").all()
    assert not table.duplicated(["municipality_id", "vote_id"]).any()
    assert set(table.loc[table.voting_date.eq(pd.Timestamp("2012-03-11", tz="UTC")), "vote_id"]) == {"10", "11"}
    assert table.loc[table.vote_id.eq("12") & table.municipality_id.eq("002"), "preparation_status"].item() == "invalid_target"
    assert table.loc[table.vote_id.eq("12") & table.municipality_id.eq("9001"), "preparation_status"].item() == "special_unit"
    assert not table.loc[table.voting_date.dt.year.eq(2026), "target_period_eligible"].any()
    assert result.coverage["unique_municipalities"] == 3
    assert result.coverage["unique_objects"] == 3
    assert result.coverage["unique_dates"] == 2
    assert result.coverage["by_date"]["2012-03-11T00:00:00+00:00"]["objects"] == 2
    assert result.coverage["by_object"]["10"]["rows"] == 1
    assert result.coverage["preparation_status"] == {
        "invalid_target": 1, "ready_for_enrichment": 1, "special_unit": 1, "subsidiary": 1,
    }
    assert set(REQUIRED).issubset(table.columns)


def test_base_table_aggregates_complete_merger_counts_before_share_and_reports_unsupported_mapping():
    outcomes = pd.DataFrame([
        {"municipality_id": "1", "vote_id": "700", "vote_date": "2018-05-01", "votes_yes": 1, "votes_no": 9,
         "is_special_unit": False, "is_tiebreak_question": False, "is_provisional": False},
        {"municipality_id": "2", "vote_id": "700", "vote_date": "2018-05-01", "votes_yes": 90, "votes_no": 10,
         "is_special_unit": False, "is_tiebreak_question": False, "is_provisional": False},
        {"municipality_id": "3", "vote_id": "700", "vote_date": "2018-05-01", "votes_yes": 9, "votes_no": 1,
         "is_special_unit": False, "is_tiebreak_question": False, "is_provisional": False},
    ])
    geography = pd.DataFrame([
        {"source_municipality_id": "1", "target_municipality_id": "9", "mapping_type": "merge",
         "crosswalk_version": "cw1", "crosswalk_evidence": "fixture"},
        {"source_municipality_id": "2", "target_municipality_id": "9", "mapping_type": "merge",
         "crosswalk_version": "cw1", "crosswalk_evidence": "fixture"},
        {"source_municipality_id": "3", "target_municipality_id": "30", "mapping_type": "split",
         "crosswalk_version": "cw1", "crosswalk_evidence": "fixture"},
    ])

    result = prepare_base_table(outcomes, geography_id="bfs-2026", source_version="fixture-v1",
                                geography_crosswalk=geography)

    merged = result.prepared.loc[result.prepared.municipality_id.eq("9")].iloc[0]
    assert (merged.yes_count, merged.no_count, merged.target_share) == (91, 19, 91 / 110)
    assert merged.harmonization_applied
    assert merged.crosswalk_version == "cw1"
    assert result.prepared.loc[result.prepared.municipality_id.eq("3"), "preparation_status"].item() == "unsupported_geography_mapping"
    assert result.join_report["geography_mapping_rows"] == 3
    assert result.coverage["preparation_status"]["unsupported_geography_mapping"] == 1


def test_base_table_marks_duplicate_keys_and_unknown_audit_values_instead_of_choosing_a_row():
    outcomes = pd.DataFrame([
        {"municipality_id": "1", "vote_id": "700", "vote_date": "2018-05-01", "votes_yes": 1, "votes_no": 9,
         "is_special_unit": False, "is_tiebreak_question": False, "is_provisional": False},
        {"municipality_id": "1", "vote_id": "700", "vote_date": "2018-05-01", "votes_yes": 2, "votes_no": 8,
         "is_special_unit": False, "is_tiebreak_question": False, "is_provisional": False},
    ])

    result = prepare_base_table(outcomes, geography_id="bfs-2026", source_version="fixture-v1")

    assert result.prepared.preparation_status.eq("duplicate_key").all()
    assert result.prepared.target_share.isna().all()


def test_base_table_reports_conflicting_object_dates_without_merging_objects_by_date():
    outcomes = pd.DataFrame([
        {"municipality_id": "1", "vote_id": "700", "vote_date": "2018-05-01", "votes_yes": 1, "votes_no": 9,
         "is_special_unit": False, "is_tiebreak_question": False, "is_provisional": False},
        {"municipality_id": "2", "vote_id": "700", "vote_date": "2018-06-01", "votes_yes": 2, "votes_no": 8,
         "is_special_unit": False, "is_tiebreak_question": False, "is_provisional": False},
    ])

    result = prepare_base_table(outcomes, geography_id="bfs-2026", source_version="fixture-v1")

    assert result.prepared.preparation_status.eq("conflicting_object_date").all()
    assert result.prepared.target_share.isna().all()


def test_base_table_is_deterministic_and_does_not_mutate_source():
    outcomes = pd.DataFrame([
        {"municipality_id": "0001", "vote_id": "700", "vote_date": "2018-05-01",
         "votes_yes": 3, "votes_no": 7, "is_special_unit": False,
         "is_tiebreak_question": False, "is_provisional": False},
    ])
    original = outcomes.copy(deep=True)

    first = prepare_base_table(outcomes, geography_id="bfs-2026", source_version="fixture-v1")
    second = prepare_base_table(outcomes, geography_id="bfs-2026", source_version="fixture-v1")

    pd.testing.assert_frame_equal(outcomes, original)
    pd.testing.assert_frame_equal(first.prepared, second.prepared)
    assert first.coverage == second.coverage


def test_base_table_keeps_2010_history_but_reports_rows_before_current_source_floor():
    outcomes = pd.DataFrame([
        {"municipality_id": "1", "vote_id": "700", "vote_date": "2009-12-31", "votes_yes": 3, "votes_no": 7,
         "is_special_unit": False, "is_tiebreak_question": False, "is_provisional": False},
        {"municipality_id": "1", "vote_id": "701", "vote_date": "2010-01-01", "votes_yes": 4, "votes_no": 6,
         "is_special_unit": False, "is_tiebreak_question": False, "is_provisional": False},
    ])

    result = prepare_base_table(outcomes, geography_id="bfs-2026", source_version="fixture-v1")

    assert result.prepared.vote_id.tolist() == ["701"]
    assert result.coverage["rows_before_source_start"] == 1
    assert result.prepared.target_period_eligible.eq(False).all()

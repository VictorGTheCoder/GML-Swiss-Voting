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
    assert table.loc[table.vote_id.eq("12") & table.municipality_id.eq("2"), "preparation_status"].item() == "invalid_target"
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
        {"municipality_id": "001", "vote_id": "700", "vote_date": "2018-05-01", "votes_yes": 1, "votes_no": 9,
         "is_special_unit": False, "is_tiebreak_question": False, "is_provisional": False},
        {"municipality_id": "2", "vote_id": "700", "vote_date": "2018-05-01", "votes_yes": 90, "votes_no": 10,
         "is_special_unit": False, "is_tiebreak_question": False, "is_provisional": False},
        {"municipality_id": "3", "vote_id": "700", "vote_date": "2018-05-01", "votes_yes": 9, "votes_no": 1,
         "is_special_unit": False, "is_tiebreak_question": False, "is_provisional": False},
    ])
    geography = pd.DataFrame([
        {"source_municipality_id": "1", "source_geography_id": "ofs-2010", "target_municipality_id": "9",
         "target_geography_id": "bfs-2026", "mapping_type": "merger", "crosswalk_version": "cw1",
         "crosswalk_evidence": "fixture", "mapping_available_at": "2010-01-01", "target_valid_from": "2010-01-01"},
        {"source_municipality_id": "2", "source_geography_id": "ofs-2010", "target_municipality_id": "9",
         "target_geography_id": "bfs-2026", "mapping_type": "merger", "crosswalk_version": "cw1",
         "crosswalk_evidence": "fixture", "mapping_available_at": "2010-01-01", "target_valid_from": "2010-01-01"},
        {"source_municipality_id": "3", "source_geography_id": "ofs-2010", "target_municipality_id": "30",
         "target_geography_id": "bfs-2026", "mapping_type": "split", "crosswalk_version": "cw1",
         "crosswalk_evidence": "fixture", "mapping_available_at": "2010-01-01", "target_valid_from": "2010-01-01"},
    ])

    result = prepare_base_table(outcomes, geography_id="bfs-2026", source_version="fixture-v1",
                                source_geography_id="ofs-2010", geography_crosswalk=geography)

    merged = result.prepared.loc[result.prepared.municipality_id.eq("9")].iloc[0]
    assert (merged.yes_count, merged.no_count, merged.target_share) == (91, 19, 91 / 110)
    assert merged.harmonization_applied
    assert merged.source_geography_id == "ofs-2010"
    assert merged.geography_id == "bfs-2026"
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

    assert result.prepared.preparation_status.tolist() == ["duplicate_key", "duplicate_key"]
    assert result.prepared.loc[result.prepared.preparation_status.eq("duplicate_key"), "target_share"].isna().all()


def test_base_table_reports_conflicting_object_dates_without_merging_objects_by_date():
    outcomes = pd.DataFrame([
        {"municipality_id": "1", "vote_id": "700", "vote_date": "2018-05-01", "votes_yes": 1, "votes_no": 9,
         "is_special_unit": False, "is_tiebreak_question": False, "is_provisional": False},
        {"municipality_id": "2", "vote_id": "700", "vote_date": "2018-06-01", "votes_yes": 2, "votes_no": 8,
         "is_special_unit": False, "is_tiebreak_question": False, "is_provisional": False},
    ])

    result = prepare_base_table(outcomes, geography_id="bfs-2026", source_version="fixture-v1")

    assert result.prepared.preparation_status.eq("conflicting_object_date").all()
    assert result.prepared.loc[result.prepared.preparation_status.eq("duplicate_key"), "target_share"].isna().all()


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


def merger_crosswalk():
    return pd.DataFrame([
        {"source_municipality_id": code, "source_geography_id": "ofs-2010", "target_municipality_id": "9",
         "target_geography_id": "bfs-2026", "mapping_type": "merger", "crosswalk_version": "cw1",
         "crosswalk_evidence": "fixture", "mapping_available_at": "2010-01-01", "target_valid_from": "2010-01-01"}
        for code in ["1", "2"]
    ])


def outcome(code, yes, no, *, version="fixture-v1", provisional=False):
    return {"municipality_id": code, "vote_id": "700", "vote_date": "2018-05-01",
            "votes_yes": yes, "votes_no": no, "is_special_unit": False,
            "is_tiebreak_question": False, "is_provisional": provisional, "source_version": version}


def test_incomplete_merger_preserves_sources_and_marks_the_missing_constituent():
    result = prepare_base_table(pd.DataFrame([outcome("1", 1, 9)]), geography_id="bfs-2026",
                                source_geography_id="ofs-2010", source_version="fixture-v1",
                                geography_crosswalk=merger_crosswalk())

    assert result.prepared.municipality_id.tolist() == ["1"]
    assert result.prepared.geography_id.eq("ofs-2010").all()
    assert result.prepared.preparation_status.eq("incomplete_geography_merger").all()


def test_duplicate_source_keys_cannot_be_summed_as_a_geography_merger():
    result = prepare_base_table(pd.DataFrame([outcome("1", 1, 9), outcome("1", 2, 8), outcome("2", 90, 10)]),
                                geography_id="bfs-2026", source_geography_id="ofs-2010",
                                source_version="fixture-v1", geography_crosswalk=merger_crosswalk())

    assert set(result.prepared.municipality_id) == {"1", "2"}
    assert result.prepared.preparation_status.tolist() == ["duplicate_key", "duplicate_key", "incomplete_geography_merger"]
    assert result.prepared.loc[result.prepared.preparation_status.eq("duplicate_key"), "target_share"].isna().all()


def test_invalid_constituent_counts_cannot_be_hidden_by_a_valid_merge_total():
    result = prepare_base_table(pd.DataFrame([outcome("1", -1, 10), outcome("2", 90, 10)]),
                                geography_id="bfs-2026", source_geography_id="ofs-2010",
                                source_version="fixture-v1", geography_crosswalk=merger_crosswalk())

    assert set(result.prepared.municipality_id) == {"1", "2"}
    assert result.prepared.preparation_status.eq("invalid_target").all()


def test_conflicting_constituent_metadata_cannot_be_selected_from_the_first_row():
    result = prepare_base_table(pd.DataFrame([outcome("1", 1, 9), outcome("2", 90, 10, provisional=True)]),
                                geography_id="bfs-2026", source_geography_id="ofs-2010",
                                source_version="fixture-v1", geography_crosswalk=merger_crosswalk())

    assert set(result.prepared.municipality_id) == {"1", "2"}
    assert result.prepared.preparation_status.eq("conflicting_merger_metadata").all()


def test_harmonized_inputs_cannot_be_crosswalked_twice():
    already_mapped = pd.DataFrame([outcome("9", 50, 50)])
    already_mapped["harmonization_applied"] = True
    already_mapped["crosswalk_version"] = "prior-cw"
    already_mapped["crosswalk_evidence"] = "prior-evidence"

    try:
        prepare_base_table(already_mapped, geography_id="bfs-2026", source_geography_id="ofs-2010",
                           source_version="fixture-v1", geography_crosswalk=merger_crosswalk())
    except ValueError as error:
        assert "harmonized" in str(error).lower()
    else:
        raise AssertionError("already harmonized outcomes must not be mapped again")


def test_conflicting_crosswalk_evidence_is_rejected_instead_of_selecting_a_constituent():
    crosswalk = merger_crosswalk()
    crosswalk.loc[1, "crosswalk_evidence"] = "different-proof"

    try:
        prepare_base_table(pd.DataFrame([outcome("1", 1, 9), outcome("2", 90, 10)]),
                           geography_id="bfs-2026", source_geography_id="ofs-2010",
                           source_version="fixture-v1", geography_crosswalk=crosswalk)
    except ValueError as error:
        assert "conflicting version, evidence" in str(error)
    else:
        raise AssertionError("inconsistent geography provenance must be rejected")

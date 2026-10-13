import json

from scripts.federal_explanations_temporal import build_forecast_text_export


def reviewed(**changes):
    row = dict(vote_id="1", vote_date="2025-06-01", full_text="Reviewed object text",
               forecast_at="2025-05-01T12:00:00+00:00", forecast_reference="official publication record",
               availability_at="2025-05-01T12:00:00+00:00", availability_reference="exact PDF archive record",
               source_sha256="a" * 64, decision_source_sha256="a" * 64,
               availability_status="CONFIRMED_PRE_VOTE", match_status="VALIDATED",
               extraction_status="EXTRACTED", semantic_status="VALIDATED")
    return row | changes


def test_export_reuses_review_gates_and_enforces_actual_forecast_cutoff(tmp_path):
    rows = [reviewed(), reviewed(vote_id="2", availability_at="2025-05-02"),
            reviewed(vote_id="3", decision_source_sha256="b" * 64),
            reviewed(vote_id="4", match_status="UNRESOLVED", object_ids=["o1", "o2"]),
            reviewed(vote_id="5", semantic_status="NOT_VALIDATED")]
    result = build_forecast_text_export(rows, tmp_path)
    assert [row["vote_id"] for row in result["documents"]] == ["1"]
    assert len(result["exclusions"]) == 4
    assert "forecast" in result["exclusions"][0]["exclusion_reason"]
    assert result["exclusions"][2]["object_ids"] == ["o1", "o2"]
    assert result["report"]["eligible_objects"] == 1
    assert result["report"]["distinct_dates"] == 1
    assert json.loads((tmp_path / "documents.json").read_text())[0]["full_text"] == "Reviewed object text"


def test_unknown_publication_evidence_exports_explicit_empty_corpus(tmp_path):
    result = build_forecast_text_export([
        reviewed(availability_at=None, availability_reference=""),
        reviewed(vote_id="2", forecast_reference=""),
    ], tmp_path)
    assert result["documents"] == []
    assert result["report"]["status"] == "empty_eligible_corpus"
    assert result["report"]["eligible_objects"] == 0
    assert result["report"]["distinct_dates"] == 0
    assert "availability evidence is unknown" in result["exclusions"][0]["exclusion_reason"]
    assert json.loads((tmp_path / "documents.json").read_text()) == []


def test_conflicting_documents_for_one_object_are_retained_for_review():
    result = build_forecast_text_export([reviewed(), reviewed(full_text="Another object section")])
    assert result["documents"] == []
    assert len(result["exclusions"]) == 2
    assert all("multiple" in row["exclusion_reason"] for row in result["exclusions"])

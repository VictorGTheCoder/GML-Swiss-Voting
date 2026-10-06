from scripts.federal_explanations_temporal import (
    decide_temporal_status,
    apply_temporal_decision,
    filter_model_eligible,
)

VOTE_DATE = "2025-06-01"
HASH = "a" * 64


def evidence(kind, date, reference="https://example.test/evidence", justification="Reviewed source"):
    return {"kind": kind, "date": date, "reference": reference, "justification": justification}


def test_confirms_public_pre_vote_evidence_and_preserves_audit_fields():
    decision = decide_temporal_status(VOTE_DATE, HASH, [evidence("public_release", "2025-05-20")])
    assert decision["status"] == "CONFIRMED_PRE_VOTE"
    assert decision["source_sha256"] == HASH
    assert decision["evidence"] == "public_release"
    assert decision["reference"] == "https://example.test/evidence"
    assert decision["justification"] == "Reviewed source"


def test_collection_closing_and_archive_migration_dates_do_not_confirm_availability():
    for kind in ("collection", "closing", "archive_migration"):
        decision = decide_temporal_status(VOTE_DATE, HASH, [evidence(kind, "2025-05-01")])
        assert decision["status"] == "INVESTIGATE"


def test_post_vote_requires_explicit_publication_or_content_change_after_vote():
    decision = decide_temporal_status(VOTE_DATE, HASH, [evidence("content_change", "2025-06-02")])
    assert decision["status"] == "POST_VOTE"
    assert decide_temporal_status(VOTE_DATE, HASH, [evidence("page_update", "2025-06-02")])["status"] == "INVESTIGATE"


def test_conflicting_temporal_evidence_is_investigate():
    decision = decide_temporal_status(VOTE_DATE, HASH, [
        evidence("public_release", "2025-05-20"), evidence("content_change", "2025-06-02", "https://example.test/change")
    ])
    assert decision["status"] == "INVESTIGATE"
    assert "contradict" in decision["justification"].lower()


def test_changed_pdf_hash_invalidates_previous_confirmation():
    prior = decide_temporal_status(VOTE_DATE, HASH, [evidence("public_release", "2025-05-20")])
    stale = apply_temporal_decision(prior, "b" * 64)
    assert stale["status"] == "INVESTIGATE"
    assert stale["decision_stale"] is True


def test_model_gate_requires_temporal_match_extraction_and_non_tiebreak():
    rows = [
        {"vote_id": "1", "availability_status": "CONFIRMED_PRE_VOTE", "source_sha256": HASH, "decision_source_sha256": HASH,
         "match_status": "VALIDATED", "extraction_status": "EXTRACTED", "semantic_status": "VALIDATED", "is_tiebreak_question": False},
        {"vote_id": "2", "availability_status": "INVESTIGATE", "match_status": "VALIDATED", "extraction_status": "EXTRACTED", "semantic_status": "VALIDATED"},
        {"vote_id": "3", "availability_status": "CONFIRMED_PRE_VOTE", "match_status": "PROPOSED", "extraction_status": "EXTRACTED", "semantic_status": "VALIDATED"},
        {"vote_id": "4", "availability_status": "CONFIRMED_PRE_VOTE", "match_status": "VALIDATED", "extraction_status": "FAILED", "semantic_status": "VALIDATED"},
        {"vote_id": "5", "availability_status": "CONFIRMED_PRE_VOTE", "match_status": "VALIDATED", "extraction_status": "EXTRACTED", "semantic_status": "VALIDATED", "is_tiebreak_question": True},
        {"vote_id": "6", "availability_status": "CONFIRMED_PRE_VOTE", "source_sha256": HASH, "decision_source_sha256": "b" * 64,
         "match_status": "VALIDATED", "extraction_status": "EXTRACTED", "semantic_status": "VALIDATED"},
    ]
    eligible, exclusions = filter_model_eligible(rows)
    assert [row["vote_id"] for row in eligible] == ["1"]
    assert {row["vote_id"] for row in exclusions} == {"2", "3", "4", "5", "6"}
    assert all(row["exclusion_reason"] for row in exclusions)


def test_empty_model_export_still_reports_exclusions():
    eligible, exclusions = filter_model_eligible([{"vote_id": "7", "availability_status": "POST_VOTE"}])
    assert eligible == []
    assert exclusions[0]["exclusion_reason"]

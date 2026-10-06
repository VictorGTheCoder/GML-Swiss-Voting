from scripts.federal_explanations_relations import build_related_vote_data


def test_linked_votes_keep_subsidiary_in_intermediate_and_exclude_it_from_model():
    objects = [
        {"vote_id": "100", "vote_date": "2026-01-01", "question_fr": "Initiative", "is_tiebreak_question": False,
         "related_vote_ids": ["101", "102"], "availability_status": "CONFIRMED_PRE_VOTE",
         "match_status": "VALIDATED", "extraction_status": "EXTRACTED", "semantic_status": "VALIDATED"},
        {"vote_id": "101", "vote_date": "2026-01-01", "question_fr": "Contre-projet", "is_tiebreak_question": False,
         "related_vote_ids": ["100", "102"], "availability_status": "CONFIRMED_PRE_VOTE",
         "match_status": "VALIDATED", "extraction_status": "EXTRACTED", "semantic_status": "VALIDATED"},
        {"vote_id": "102", "vote_date": "2026-01-01", "question_fr": "Question subsidiaire", "is_tiebreak_question": True,
         "related_vote_ids": ["100", "101"], "availability_status": "CONFIRMED_PRE_VOTE",
         "match_status": "VALIDATED", "extraction_status": "EXTRACTED", "semantic_status": "VALIDATED"},
    ]
    sections = [
        {"section_id": "common", "title": "Propositions", "summary_official": "Résumé partagé"},
        {"section_id": "common", "title": "Propositions", "summary_official": "Résumé partagé"},
    ]
    links = [{"vote_id": vote_id, "section_id": "common"} for vote_id in ("100", "101", "102")]

    result = build_related_vote_data(objects, sections, links)

    assert result["votes_intermediate"].vote_id.tolist() == ["100", "101", "102"]
    assert result["votes_intermediate"].loc[2, "is_tiebreak_question"]
    assert result["votes_intermediate"].loc[2, "related_vote_ids"] == ["100", "101"]
    assert result["sections"].section_id.tolist() == ["common"]
    assert len(result["section_links"]) == 3
    assert set(result["model"].vote_id) == {"100", "101"}
    assert "section and question counts may differ" in result["report"].lower()


def test_vote_can_link_multiple_sections_and_relationships_are_reciprocal():
    objects = [
        {"vote_id": "200", "is_tiebreak_question": False, "related_vote_ids": ["201"]},
        {"vote_id": "201", "is_tiebreak_question": False, "related_vote_ids": ["200"]},
    ]
    sections = [{"section_id": "shared"}, {"section_id": "initiative-only"}, {"section_id": "other-only"}]
    links = [
        {"vote_id": "200", "section_id": "shared"},
        {"vote_id": "201", "section_id": "shared"},
        {"vote_id": "200", "section_id": "initiative-only"},
        {"vote_id": "201", "section_id": "other-only"},
    ]

    result = build_related_vote_data(objects, sections, links)

    assert len(result["sections"]) == 3
    assert set(result["section_links"].query("vote_id == '200'").section_id) == {"shared", "initiative-only"}
    assert result["related_votes"].to_dict("records") == [
        {"vote_id": "200", "related_vote_id": "201"},
        {"vote_id": "201", "related_vote_id": "200"},
    ]


def test_recommendations_retain_raw_text_and_normalize_only_clear_targets():
    objects = [{
        "vote_id": "300", "is_tiebreak_question": False, "related_vote_ids": [],
        "question_fr": "Initiative", "initiative_title": "Initiative", "counterproposal_title": "Contre-projet",
        "council_recommendation_raw": "Rejeter l’initiative et accepter le contre-projet.",
        "parliament_recommendation_raw": "Pas de recommandation.",
    }]

    result = build_related_vote_data(objects, [], [])
    row = result["votes_intermediate"].iloc[0]

    assert row.council_recommendation_raw == "Rejeter l’initiative et accepter le contre-projet."
    assert row.council_recommendation_target is None
    assert row.council_recommendation_reason == "multiple_targets"
    assert row.parliament_recommendation_raw == "Pas de recommandation."
    assert row.parliament_recommendation_target is None
    assert row.parliament_recommendation_reason == "explicit_no_recommendation"


def test_single_clear_recommendation_is_normalized_for_question_target():
    objects = [{"vote_id": "400", "is_tiebreak_question": False, "related_vote_ids": [],
                "question_fr": "Initiative", "initiative_title": "Initiative",
                "council_recommendation_raw": "Le Conseil fédéral recommande de rejeter l’initiative."}]

    result = build_related_vote_data(objects, [], [])
    row = result["votes_intermediate"].iloc[0]

    assert row.council_recommendation_target == "REJECT_INITIATIVE"
    assert row.council_recommendation_reason == "clear_single_target"

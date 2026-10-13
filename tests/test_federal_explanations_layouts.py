import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.federal_explanations.federal_explanations_layouts import (
    build_coverage,
    detect_layout,
    extract_objects,
    propose_matches,
)


def test_modern_multi_object_layout_keeps_objects_and_pages_in_order():
    pages = [
        "Objet 1: Initiative sur les soins\nRésumé officiel: Résumé un",
        "Suite de l’objet 1, passage distinct.",
        "Objet 2: Loi sur le climat\nRésumé officiel: Résumé deux",
        "Objet 1: Initiative sur les soins\nTexte complet: Passage final un",
    ]

    parsed = extract_objects(pages)

    assert parsed["layout"] == "MODERN"
    assert [(item["order"], item["title"]) for item in parsed["objects"]] == [
        (1, "Initiative sur les soins"), (2, "Loi sur le climat")
    ]
    assert parsed["objects"][0]["object_id"] != parsed["objects"][1]["object_id"]
    assert parsed["objects"][0]["source_pages"] == [1, 2, 4]
    assert [passage["pages"] for passage in parsed["objects"][0]["passages"]] == [[1, 2], [4]]


def test_pre_2018_layout_is_recognized_with_distinct_object_order():
    parsed = extract_objects([
        "Premier objet : Initiative pour les transports\nL’objet soumis au vote est décrit ici.",
        "Deuxième objet : Loi fédérale sur la sécurité alimentaire\nExplications détaillées.",
    ])

    assert parsed["layout"] == "LEGACY"
    assert [(item["order"], item["title"]) for item in parsed["objects"]] == [
        (1, "Initiative pour les transports"),
        (2, "Loi fédérale sur la sécurité alimentaire"),
    ]
    assert parsed["objects"][0]["source_pages"] == [1]
    assert parsed["objects"][1]["source_pages"] == [2]


def test_legacy_heading_with_title_wrapped_to_following_lines():
    parsed = extract_objects(["Votation populaire du 28 février 2016\nPremier objet\nInitiative populaire « Pour le couple\net la famille – Non à la pénalisation\ndu mariage »\nLa question à laquelle vous devez répondre est la suivante :\nAcceptez-vous l’initiative ?"])
    assert parsed["layout"] == "LEGACY"
    assert parsed["objects"][0]["title"] == "Initiative populaire « Pour le couple et la famille – Non à la pénalisation du mariage »"
    assert "La question à laquelle" in parsed["objects"][0]["passages"][0]["text"]


def test_bare_objet_heading_uses_following_title():
    parsed = extract_objects(["Objet\nInitiative populaire « Pour la sortie programmée de l’énergie nucléaire »\nLa question à laquelle vous devez répondre est la suivante :\nAcceptez-vous l’initiative ?"])
    assert parsed["objects"][0]["title"].startswith("Initiative populaire")


def test_single_object_without_explicit_objet_label_uses_question_section():
    parsed = extract_objects(["Initiative populaire\n« Pour la protection face à la violence des armes »\nLa question à laquelle vous devez répondre est la suivante:\nAcceptez-vous l’initiative populaire ?"])
    assert parsed["objects"][0]["title"] == "Initiative populaire « Pour la protection face à la violence des armes »"
    assert "La question à laquelle" in parsed["objects"][0]["passages"][0]["text"]


def test_object_ids_are_bound_to_source_version():
    pages = ["Objet 1: Loi test"]

    first = extract_objects(pages, source_id="bk-vote", source_sha256="a" * 64)
    revised = extract_objects(pages, source_id="bk-vote", source_sha256="b" * 64)

    assert first["objects"][0]["object_id"] != revised["objects"][0]["object_id"]


def test_unknown_structure_stays_unrecognized():
    assert detect_layout(["Introduction générale", "Un paragraphe sans titre structurant."]) == "UNRECOGNIZED"
    assert extract_objects(["Introduction générale"])["objects"] == []


def test_similarity_only_proposes_candidates_and_does_not_validate_ambiguous_match():
    match = propose_matches(
        "Initiative sur les soins",
        [
            {"vote_id": "6001", "question_fr": "Initiative sur les soins"},
            {"vote_id": "6002", "question_fr": "Initiative pour les soins"},
        ],
    )

    assert match["status"] == "AMBIGUOUS"
    assert len(match["candidates"]) == 2
    assert all(candidate["status"] == "PROPOSED" for candidate in match["candidates"])


def test_missing_expected_objects_remain_in_coverage_and_are_excluded():
    coverage = build_coverage(
        ["6001", "6002"],
        [{"object_id": "obj-1", "ofs_vote_id": "6001", "status": "VALIDATED"}],
    )

    assert coverage == [
        {"vote_id": "6001", "coverage_status": "FOUND", "object_ids": ["obj-1"], "model_excluded": False, "reason": ""},
        {"vote_id": "6002", "coverage_status": "MISSING", "object_ids": [], "model_excluded": True, "reason": "no extracted object linked to OFS vote_id"},
    ]

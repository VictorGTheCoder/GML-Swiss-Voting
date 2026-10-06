"""Contracts for source identity, shared sections and conservative model eligibility."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import federal_explanations as explanations


def test_archive_dates_are_scrutin_dates_not_asset_update_dates():
    html = '''<a href="/dam/fr/a.pdf">2024-11-24 - Explications du Conseil fédéral
    PDF 28 mai 2026</a><a href="/dam/fr/a.pdf">2024-11-24 - Explications</a>
    <a href="/other">Navigation</a>'''
    records = explanations.parse_archive(html)
    assert len(records) == 1
    assert records[0]["vote_date"] == "2024-11-24"
    assert records[0]["source_url"] == "https://www.bk.admin.ch/dam/fr/a.pdf"


def test_archive_rejects_conflicting_brochures_for_same_date():
    with pytest.raises(ValueError, match="Conflicting"):
        explanations.parse_archive('''<a href="/a.pdf">2024-11-24 - Explications</a>
        <a href="/b.pdf">2024-11-24 - Explications</a>''')


def test_modern_sections_include_summary_and_detail_without_other_objects():
    toc = '''3\nPremier objet\nDeuxième objet\nInitiative populaire « A »
    En bref 4 – 5 En détail 8 Arguments 10 Texte soumis au vote 12
    Modification de la loi B
    En bref 6 – 7 En détail 16 Arguments 18 Texte soumis au vote 20'''
    sections = explanations.section_ranges(toc, page_count=24, object_count=2)
    assert sections[0]["page_numbers"] == [4, 5, *range(8, 16)]
    assert sections[1]["page_numbers"] == [6, 7, *range(16, 24)]
    assert sections[0]["title"] == 'Initiative populaire « A »'
    assert not set(sections[0]["page_numbers"]) & set(sections[1]["page_numbers"])


def test_legacy_shared_section_is_not_split_by_number_of_ofs_questions():
    toc = '''Sur quoi vote-t-on ? Arrêté A Explications pages 4–11
    Texte soumis au vote page 8 Initiative et contre-projet B
    Explications pages 12–61 Texte de la loi pages 26–61'''
    sections = explanations.section_ranges(toc, page_count=64, object_count=3)
    assert [s["page_numbers"] for s in sections] == [list(range(4, 12)), list(range(12, 62))]


def test_collection_timestamp_cannot_confirm_pre_vote():
    assert explanations.temporal_status("2024-11-24", "abc", None) == "INVESTIGATE"
    with pytest.raises(ValueError, match="evidence"):
        explanations.temporal_status("2024-11-24", "abc", {
            "source_sha256": "abc", "status": "CONFIRMED_PRE_VOTE"})


def test_temporal_review_is_bound_to_file_and_date():
    review = {"source_sha256": "abc", "status": "CONFIRMED_PRE_VOTE",
              "evidence_date": "2024-10-01", "evidence_url": "https://www.bk.admin.ch/proof",
              "evidence_note": "Evidence establishes this file version", "reviewer": "team"}
    assert explanations.temporal_status("2024-11-24", "abc", review) == "CONFIRMED_PRE_VOTE"
    with pytest.raises(ValueError, match="hash"):
        explanations.temporal_status("2024-11-24", "changed", review)
    with pytest.raises(ValueError, match="before"):
        explanations.temporal_status("2024-11-24", "abc", dict(review, evidence_date="2024-11-24"))


def test_model_gate_excludes_subsidiary_and_unreviewed_extractions():
    base = {"availability_status": "CONFIRMED_PRE_VOTE", "matching_status": "VALIDATED",
            "extraction_status": "VALIDATED", "is_tiebreak_question": False}
    assert explanations.model_eligible(base)
    for change in [{"availability_status": "INVESTIGATE"}, {"availability_status": "POST_VOTE"},
                   {"is_tiebreak_question": True}, {"matching_status": "PROPOSED"},
                   {"extraction_status": "NEEDS_REVIEW"}]:
        assert not explanations.model_eligible(dict(base, **change))


def test_fuzzy_titles_do_not_silently_validate_matching():
    sections = [{"section_key": "s1", "title": "Initiative populaire pour le logement"}]
    match = explanations.match_title("Initiative pour le logement abordable", sections)
    assert match["matching_status"] == "PROPOSED"
    assert match["section_key"] == "s1"


def test_duplicate_titles_require_review():
    sections = [{"section_key": "s1", "title": "Loi A"},
                {"section_key": "s2", "title": "Loi A"}]
    assert explanations.match_title("Loi A", sections)["matching_status"] == "AMBIGUOUS"

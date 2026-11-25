"""TOC aliases are identity checks, not ordinal assumptions or admission."""

from scripts.modeling.toc_audit_v122c import review_entry

ENTRY = {"terms": [["taxe", "valeur"]], "summary": [4, 5], "detail": 8,
         "arguments": 10, "legal": 12}


def test_title_and_pages():
    pages = {4: "Taxe sur la valeur ajoutée. " * 20, 5: "Explication du projet. " * 20}
    record = review_entry(ENTRY, {"2": "Taxe sur la valeur ajoutée"}, pages)
    assert record["status"] == "unique_candidate"
    assert record["vote_ids"] == ["2"]
    assert len(record["page_hashes"]) == 2
    assert all("text" not in p for p in record["page_hashes"])


def test_missing_and_ambiguous():
    titles = {"2": "Taxe sur la valeur ajoutée"}
    assert review_entry(ENTRY, titles, {})["status"] == "missing_page"
    assert review_entry(ENTRY, {**titles, "3": "Taxe sur la valeur"}, {})["status"] == "unresolved_title"


def test_shared_separate_status():
    pages = {4: "Taxe sur la valeur ajoutée. " * 20, 5: "Explication du projet. " * 20}
    record = review_entry({**ENTRY, "shared": "common"}, {"2": "Taxe sur la valeur"}, pages)
    assert record["status"] == "shared_candidate"

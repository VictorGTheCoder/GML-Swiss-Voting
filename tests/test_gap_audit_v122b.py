"""Candidate leads are not admission; ambiguity is retained explicitly."""
from scripts.modeling.gap_audit_v122b import page_diagnostics

TITLES = {"1": ["initiative pour la protection des paysages"],
          "2": ["loi sur les transports publics nationaux"]}


def page(text, number=4):
    return {"page_number": number, "text": text + " " + "Une explication du projet. " * 20}


def test_strict_and_no_raw_text():
    result = page_diagnostics([page("En bref initiative pour la protection des paysages")],
                              TITLES, "1")
    assert result[0]["kind"] == "strict_candidate"
    assert len(result[0]["sha256"]) == 64
    assert "text" not in result[0]


def test_ambiguity_and_missing_marker():
    result = page_diagnostics([
        page("En bref initiative pour la protection des paysages et loi sur les transports publics nationaux"),
        page("initiative pour la protection des paysages", 5),
        page("En bref initiative pour la protection des paysages", 1),
    ], TITLES, "1")
    assert [r["kind"] for r in result] == ["other_object_title", "no_summary_marker"]
    assert result[0]["other_ids"] == ["2"]

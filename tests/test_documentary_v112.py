"""Tests for independent source matching and literal context."""
import pandas as pd

from scripts.modeling.documentary_audit_v112 import (
    independent_pages,
    mechanism_text,
    question_text,
    variant_corpus,
)


def page(number, text):
    return {"page_number": number, "text": text + " " + "Explication générale. " * 12}


def test_pages_require_unique_exact_title():
    titles = {"a": ["Révision de la fiscalité des entreprises"], "b": ["Loi sur les allocations familiales"]}
    pages = [
        page(2, "En bref Révision de la fiscalité des entreprises"),
        page(3, "En bref fiscalité entreprises révision"),
        page(4, "En détail Révision de la fiscalité des entreprises Loi sur les allocations familiales"),
        page(5, "En détail Révision de la fiscalité des entreprises"),
    ]
    picked = independent_pages(pages, titles)
    assert [n for n, _ in picked["a"]] == [2, 5]
    assert picked["b"] == []


def test_question_does_not_invent_direction():
    text = "Contexte. Acceptez-vous la modification de la loi sur les impôts? Suite."
    assert question_text(text) == "Acceptez-vous la modification de la loi sur les impôts?"
    assert not question_text("La loi sur les impôts augmente les recettes.")


def test_mechanisms_retain_sentence_context():
    text = "Présentation. Le projet supprime certaines taxes mais augmente les contributions."
    assert mechanism_text(text) == "Le projet supprime certaines taxes mais augmente les contributions."


def test_missing_page_falls_back_to_title():
    data = pd.DataFrame({"title_text": ["Titre A", "Titre B"], "vote_date": pd.to_datetime(["2020-01-01"] * 2),
                         "question_text": ["", "Question?"]}, index=["a", "b"])
    got = variant_corpus(data, "question_text")
    assert got.document_text.tolist() == ["Titre A", "Titre B\nQuestion?"]
    assert got.usable_summary.tolist() == [False, True]

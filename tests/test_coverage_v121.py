"""Coverage matching must depend only on source availability."""

import pandas as pd

from scripts.modeling.coverage_v121 import matched_documents


def test_common_support_and_union():
    audit = pd.DataFrame({
        "title_text": ["A", "B", "C", "D"],
        "vote_date": pd.to_datetime(["2020-01-01"] * 4),
        "original_text": ["A old", "B old", "C invalid", "D invalid"],
        "original_covered": [True, True, False, False],
        "exact_text": ["A verified", "", "C verified", ""],
    }, index=["a", "b", "c", "d"])
    docs = matched_documents(audit)
    assert docs["matched_original"].usable_summary.tolist() == [True, False, False, False]
    assert docs["matched_exact"].usable_summary.equals(docs["matched_original"].usable_summary)
    assert docs["matched_original"].document_text.tolist() == ["A old", "B", "C", "D"]
    assert docs["matched_exact"].document_text.tolist() == ["A\nA verified", "B", "C", "D"]
    assert docs["union_prefer_exact"].usable_summary.tolist() == [True, True, True, False]
    assert docs["union_prefer_exact"].document_text.tolist() == ["A\nA verified", "B old", "C\nC verified", "D"]
    assert docs["title_only"].document_text.tolist() == ["A", "B", "C", "D"]
    assert not docs["title_only"].usable_summary.any()
    assert audit.original_text.iloc[-1] == "D invalid"


def test_no_common_documents():
    audit = pd.DataFrame({
        "title_text": ["A"],
        "vote_date": pd.to_datetime(["2020-01-01"]),
        "original_text": ["A old"],
        "original_covered": [True],
        "exact_text": [""],
    })
    docs = matched_documents(audit)
    assert docs["matched_original"].document_text.tolist() == ["A"]
    assert docs["matched_exact"].document_text.tolist() == ["A"]
    assert docs["union_prefer_exact"].document_text.tolist() == ["A old"]

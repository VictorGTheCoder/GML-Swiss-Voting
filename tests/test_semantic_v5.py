"""V5 historical YES effects: metadata fidelity and strictly train-only encoding."""

from __future__ import annotations

import copy
from pathlib import Path

import pandas as pd
import pytest

from scripts.modeling.semantic_features_v4 import load_annotations
from scripts.modeling.semantic_labels_v5 import (
    HISTORICAL,
    V4,
    build_coarse_table,
    coarse_tags_historical,
    encode_tags,
    load_history,
    validate_history,
    vocabulary,
)

ROOT = Path(__file__).resolve().parents[1]


def object_table():
    return pd.read_csv(
        ROOT / "data/processed/municipal_v3/object_features.csv",
        dtype={"vote_id": str, "vote_key": str},
        usecols=["vote_id", "vote_date"],
    )


def test_historical_corpus_source_evidence_and_real_vote_ids():
    history = load_history(HISTORICAL)
    assert len(history["votes"]) == 80
    assert len(history["sources"]) == 33
    assert sum(len(v["effects"]) for v in history["votes"]) == 81
    dates = pd.to_datetime([v["vote_date"] for v in history["votes"]])
    assert dates.min().year == 2005
    assert dates.max().year == 2015
    assert history["status"] == "first_pass_source_supported_not_independently_reviewed"
    assert all(v["review_status"] == "first_pass_not_independently_reviewed"
               for v in history["votes"])
    assert all(s["published_at_verified"] is None for s in history["sources"].values())
    assert all(s["url"].startswith("https://www.bk.admin.ch/")
               for s in history["sources"].values())
    actual = object_table().set_index("vote_id").vote_date
    for row in history["votes"]:
        assert pd.Timestamp(actual[row["vote_id"]]) == pd.Timestamp(row["vote_date"])


def test_source_mechanisms_are_distinct_from_themes():
    history = load_history()
    by_id = {v["vote_id"]: v for v in history["votes"]}
    freedom = by_id["5190"]
    kinds = {e["family"] for e in freedom["effects"]}
    assert kinds == {"international_agreement", "labour_rule"}
    assert "mechanism_treaty" in coarse_tags_historical(freedom)
    assert "mechanism_employment_rule" in coarse_tags_historical(freedom)
    cap = by_id["5550"]
    tax = by_id["5900"]
    assert "mechanism_legal_restriction" in coarse_tags_historical(cap)
    assert "mechanism_taxation" in coarse_tags_historical(tax)
    assert "domain_housing" in coarse_tags_historical(cap)


def test_uncertain_source_is_unknown_instead_of_pseudolabel():
    history = load_history()
    row = next(v for v in history["votes"] if v["vote_id"] == "5340")
    assert row["effects"][0]["evidence_confidence"] == "medium"
    assert coarse_tags_historical(row) == set()


def test_coarse_combination_is_exactly_matched_and_target_blind():
    history = load_history()
    current = load_annotations(V4)
    objects = object_table()
    features = build_coarse_table(objects, history, current)
    assert len(features) == len(objects) == 380
    assert features.vote_id.tolist() == objects.vote_id.tolist()
    assert features.coarse_documented.sum() == 121  # 79 high historical + 42 pilot
    assert features.annotation_origin.value_counts().to_dict() == {
        "history": 79, "v4": 42, "unreviewed": 1, "unannotated": 258,
    }
    modern = features.set_index("vote_id").loc["6410", "coarse_tags"].split("|")
    assert "mechanism_public_finance" in modern
    assert "mechanism_legal_restriction" not in modern
    assert "mechanism_legal_restriction" in (
        features.set_index("vote_id").loc["6420", "coarse_tags"].split("|")
    )
    modified = objects.assign(yes_share=0.25, prediction=0.75, popular_result=1)
    pd.testing.assert_frame_equal(features, build_coarse_table(modified, history, current))


def test_zero_annotations_in_old_years_are_marked_unknown():
    table = build_coarse_table(object_table(), load_history(), load_annotations(V4))
    objects = object_table()
    before_2005 = table.loc[pd.to_datetime(objects.vote_date).dt.year.lt(2005)]
    assert before_2005.coarse_documented.eq(0).all()
    assert before_2005.coarse_tags.eq("").all()


@pytest.mark.parametrize("invalid", ["outcome", "duplicate", "date", "review", "source", "unknown_domain", "unknown_family"])
def test_rejects_metadata_errors_and_outcomes(invalid):
    bad = copy.deepcopy(load_history())
    if invalid == "outcome":
        bad["votes"][0]["effects"][0]["popular_result"] = 62
    elif invalid == "duplicate":
        bad["votes"].append(copy.deepcopy(bad["votes"][0]))
    elif invalid == "date":
        bad["votes"][0]["vote_date"] = "2025-06-05"
    elif invalid == "review":
        bad["votes"][0]["review_status"] = "approved"
    elif invalid == "source":
        bad["sources"]["2005-06"]["url"] = "https://untrusted.example.com"
    elif invalid == "unknown_domain":
        bad["votes"][0]["effects"][0]["domain"] = "unsupported_domain"
    else:
        bad["votes"][0]["effects"][0]["family"] = "unmapped_rare_rule"
    with pytest.raises((ValueError, TypeError)):
        validate_history(bad)


def test_missing_or_corrupt_identity_does_not_silently_match():
    rows = object_table()
    history = load_history()
    current = load_annotations(V4)
    with pytest.raises(ValueError):
        build_coarse_table(rows.loc[rows.vote_id.ne('5170')], history, current)
    rows.loc[rows.vote_id.eq("5170"), "vote_date"] = "2019-01-01"
    with pytest.raises(ValueError, match="mismatch"):
        build_coarse_table(rows, history, current)


def test_train_only_vocabulary_and_frequency_threshold():
    train = pd.DataFrame({
        "coarse_tags": [
            "mechanism_taxation|domain_taxation",
            "mechanism_taxation|domain_taxation",
            "mechanism_taxation|domain_welfare",
            "mechanism_rare|domain_education",
        ]
    })
    validation = pd.DataFrame({"coarse_tags": ["mechanism_unknown_future"]})
    vocab = vocabulary(train, min_count=3)
    assert vocab == ["mechanism_taxation"]
    assert encode_tags(validation, vocab).eq(0).all().all()
    assert encode_tags(train, vocab).dtypes.tolist() == ["uint8"]
    with pytest.raises(ValueError):
        vocabulary(train, min_count=0)


def test_2016_training_has_nonzero_historical_coverage():
    history = load_history()
    current = load_annotations(V4)
    objects = object_table()
    table = objects.merge(build_coarse_table(objects, history, current),
                          on="vote_id", how="left", validate="one_to_one")
    before = table[pd.to_datetime(table.vote_date).lt("2016-01-01")]
    assert before.coarse_documented.sum() == 79
    assert before.vote_id.nunique() >= 79


def test_historical_annotation_edition_is_not_claimed_strict():
    history = load_history()
    assert "not_independently_reviewed" in history["status"]
    assert "not been authenticated" in history["limitations"].lower()
    assert all(s["editorial_cutoff"] is None for s in history["sources"].values())

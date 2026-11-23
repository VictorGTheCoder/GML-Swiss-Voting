"""Contract checks for compact multi-topic features and evidence-bound YES effects."""

import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.modeling.semantic_features_v4 import (
    annotation_tags,
    build_semantic_table,
    build_topic_table,
    canonical_topics,
    encode_multihot,
    fit_vocabulary,
    load_annotations,
    topic_features,
    validate_annotation_document,
)

ANNOTATIONS = Path(__file__).resolve().parents[1] / "data/annotations/yes_effects_v4.json"


def fixture_document():
    full = load_annotations(ANNOTATIONS)
    two = [v for v in full["votes"] if v["vote_id"] in ("6410", "6420")]
    assert len(two) == 2
    return {**full, "votes": two}


def test_curated_corpus_is_source_backed_and_has_distinct_effects():
    document = load_annotations(ANNOTATIONS)
    assert len(document["votes"]) == 42
    assert len(document["sources"]) == 13
    assert sum(len(v["effects"]) for v in document["votes"]) == 45
    assert all(v["independent_review"] == "pending" for v in document["votes"])
    assert all(source["published_at"] is None for source in document["sources"].values())
    assert document["strict_forecast_ready"] is False


def test_water_direct_payment_conditionality_is_not_general_pesticide_ban():
    document = fixture_document()
    a, b = sorted(document["votes"], key=lambda v: v["vote_id"])
    assert a["vote_id"] == "6410" and b["vote_id"] == "6420"
    a_tags, b_tags = set(annotation_tags(a).split("|")), set(annotation_tags(b).split("|"))
    assert "instrument_subsidy_conditionality" in a_tags
    assert "quantity_direct_payment_eligibility" in a_tags
    assert "instrument_prohibition" in b_tags
    assert "quantity_synthetic_pesticides_ban" in b_tags
    assert "instrument_prohibition" not in a_tags


def test_topics_collapse_three_slots_to_leaf_antichain():
    row = {
        "extra_domain_tokens_1": "4|6|4",
        "extra_domain_tokens_2": "6.2|4.2|6.1",
        "extra_domain_tokens_3": "6.12|4.24",
    }
    assert canonical_topics(row) == "4.24|6.2|6.12"
    assert canonical_topics({**row, "extra_domain_tokens_2": "4.2|6.1|6.2"}) == canonical_topics(row)
    assert set(topic_features(canonical_topics(row), hierarchy=True).split("|")) == {
        "4", "4.2", "4.24", "6", "6.1", "6.2", "6.12",
    }
    assert topic_features("4.24|6.12", hierarchy=False) == "4.24|6.12"


def test_topic_build_rejects_bad_source_or_duplicate_object():
    frame = pd.DataFrame({
        "vote_id": ["x", "y"],
        "extra_domain_tokens_1": ["4", "4"],
        "extra_domain_tokens_2": ["4.2", "4.2"],
        "extra_domain_tokens_3": ["4.24", "4.21"],
    })
    assert build_topic_table(frame).topic_leaves.tolist() == ["4.24", "4.21"]
    with pytest.raises(ValueError):
        build_topic_table(frame.assign(vote_id=["x", "x"]))
    frame.loc[0, "extra_domain_tokens_3"] = "4.xx"
    with pytest.raises(ValueError):
        build_topic_table(frame)


def test_semantics_are_null_not_negative_when_unknown():
    document = fixture_document()
    objects = pd.DataFrame({
        "vote_id": ["6410", "6420", "9990"],
        "vote_date": pd.to_datetime(["2021-06-13", "2021-06-13", "2022-01-01"]),
    })
    output = build_semantic_table(objects, document)
    assert output.semantic_documented.tolist() == [1, 1, 0]
    assert output.semantic_tags.iloc[2] == ""
    assert "signed_direct_payment_eligibility_restrict" in output.semantic_tags.iloc[0]
    assert "signed_synthetic_pesticides_ban_introduce" in output.semantic_tags.iloc[1]


def test_no_target_field_or_outcome_can_enter_encoding():
    doc = fixture_document()
    objects = pd.DataFrame({"vote_id": ["6410", "6420"], "vote_date": pd.to_datetime(["2021-06-13"] * 2)})
    a = build_semantic_table(objects, doc)
    b = build_semantic_table(objects.assign(yes_share=[0.1, 0.9]), doc)
    pd.testing.assert_frame_equal(a, b)
    broken = copy.deepcopy(doc)
    broken["votes"][0]["popular_result"] = 99
    with pytest.raises(ValueError):
        validate_annotation_document(broken)
    broken = copy.deepcopy(doc)
    broken["votes"][0]["effects"][0]["volkja"] = 12
    with pytest.raises(ValueError):
        validate_annotation_document(broken)


def test_strict_identity_date_and_source_gates():
    doc = fixture_document()
    objects = pd.DataFrame({"vote_id": ["6410", "6420"], "vote_date": pd.to_datetime(["2021-06-13"] * 2)})
    with pytest.raises(ValueError, match="mismatch"):
        build_semantic_table(objects.assign(vote_date=pd.to_datetime(["2021-06-12", "2021-06-13"])), doc)
    with pytest.raises(ValueError):
        build_semantic_table(objects.iloc[[0, 0]], doc)
    with pytest.raises(ValueError):
        build_semantic_table(objects.iloc[[0]], doc)
    bad = copy.deepcopy(doc)
    bad["sources"]["2021-06"]["editorial_cutoff"] = "2021-06-14"
    with pytest.raises(ValueError):
        validate_annotation_document(bad)
    bad = copy.deepcopy(doc)
    bad["sources"]["2021-06"]["url"] = "https://example.com"
    with pytest.raises(ValueError):
        validate_annotation_document(bad)


def test_unknown_and_mixed_directions_cannot_be_overclaimed():
    document = fixture_document()
    for direction in ("neutral", "unknown", "yes_is_good", "pro_environment"):
        bad = copy.deepcopy(document)
        bad["votes"][0]["effects"][0]["direction"] = direction
        with pytest.raises(ValueError):
            validate_annotation_document(bad)
    bad = copy.deepcopy(document)
    bad["votes"][0]["effects"][0]["evidence_kind"] = "inferred_voter_motivation"
    with pytest.raises(ValueError):
        validate_annotation_document(bad)


def test_conditional_ballots_preserved_in_annotation():
    doc = load_annotations(ANNOTATIONS)
    a = next(v for v in doc["votes"] if v["vote_id"] == "6590")
    b = next(v for v in doc["votes"] if v["vote_id"] == "6600")
    assert a["effects"][0]["conditional_on"] == ["6600"]
    assert b["effects"][0]["conditional_on"] == ["6590"]
    assert "conditional_on_other_ballot" in annotation_tags(a)


def test_multi_hot_learns_only_training_vocabulary():
    train = pd.DataFrame({"semantic_tags": ["domain_agriculture|instrument_subsidy_conditionality", ""]})
    later = pd.DataFrame({"semantic_tags": ["instrument_prohibition|domain_environment", ""]})
    vocab = fit_vocabulary(train, "semantic_tags")
    assert "instrument_prohibition" not in vocab
    z = encode_multihot(later, "semantic_tags", vocab, "sem")
    assert "sem_instrument_prohibition" not in z
    assert (z.to_numpy() == 0).all()
    assert all(str(t) == "uint8" for t in z.dtypes)
    with pytest.raises(ValueError):
        encode_multihot(later, "semantic_tags", ["a", "a"], "sem")


def test_document_round_trip_explicit_no_prospectively_authenticated_claim():
    loaded = json.loads(ANNOTATIONS.read_text(encoding="utf-8"))
    validate_annotation_document(loaded)
    assert loaded["data_status"] == "source_reviewed_first_pass_independent_review_pending"
    assert all(v["source_review"] == "checked_against_prevote_booklet" for v in loaded["votes"])

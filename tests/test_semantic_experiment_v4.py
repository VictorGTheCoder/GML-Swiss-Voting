"""No-leakage tests for the semantic campaign's fold-specific feature encoding."""

import pandas as pd
import pytest

from scripts.modeling.semantic_experiment_v4 import VARIANTS, fold_features


def example():
    train = pd.DataFrame({
        "vote_id": ["1000", "1000", "2000", "2000"],
        "municipality_id": ["A", "B", "A", "B"],
        "yes_share": [0.3, 0.4, 0.1, 0.2],
        "object_legal_form": ["1", "1", "3", "3"],
        "object_domain_1": ["4", "4", "6", "6"],
        "political_domain_d1e2": ["4.2", "4.2", "6.1", "6.1"],
        "num": [1, 1, 2, 2],
    })
    evaluation = pd.DataFrame({
        "vote_id": ["3000", "3000"], "municipality_id": ["A", "B"],
        "yes_share": [0.8, 0.9], "object_legal_form": ["3", "3"],
        "object_domain_1": ["4", "4"], "political_domain_d1e2": ["4.2", "4.2"],
        "num": [3, 3],
    })
    extras = pd.DataFrame({
        "vote_id": ["1000", "2000", "3000"],
        "extra_domain_tokens_1": ["4", "6", "4"],
        "extra_domain_tokens_2": ["4.2", "6.1", "4.2"],
        "extra_domain_tokens_3": ["4.24", "6.12", "4.29"],
        "topic_leaves": ["4.24", "6.12", "4.29"],
        "topic_nodes": ["4|4.2|4.24", "6|6.1|6.12", "4|4.2|4.29"],
        "semantic_tags": ["domain_agriculture|instrument_subsidy_conditionality",
                          "domain_environment", "instrument_prohibition"],
        "semantic_documented": [1, 1, 1],
    })
    return train, evaluation, extras


@pytest.mark.parametrize("variant", VARIANTS)
def test_fold_only_uses_past_topics_and_semantic_tags(variant):
    train, evaluation, extras = example()
    a, b, numeric, categorical, vocab, coverage = fold_features(
        train, evaluation, extras, ["num"], [
            "object_legal_form", "object_domain_1", "political_domain_d1e2"
        ], variant)
    assert len(a) == 4 and len(b) == 2
    assert a.municipality_id.tolist() == train.municipality_id.tolist()
    assert b.yes_share.tolist() == evaluation.yes_share.tolist()
    assert "object_domain_1" not in categorical
    assert "political_domain_d1e2" not in categorical
    assert "object_legal_form" in categorical
    assert coverage["evaluation_annotated_objects"] == 1
    assert len(set(numeric + categorical)) == len(numeric + categorical)
    if "effects" in variant:
        assert "instrument_prohibition" not in vocab["semantics"]
        assert "effect_instrument_prohibition" not in numeric
        assert "effect_instrument_subsidy_conditionality" in numeric
        assert b["effect_instrument_subsidy_conditionality"].eq(0).all()
        assert a["effect_instrument_subsidy_conditionality"].iloc[0] == 1
    elif variant == "canonical_leaf":
        assert "4.29" not in vocab["topics"]
        assert "topic_4_29" not in numeric


def test_future_targets_cannot_affect_semantic_features():
    train, evaluation, extras = example()
    first = fold_features(train, evaluation, extras, ["num"], ["object_legal_form"], "canonical_leaf_plus_effects")
    other = fold_features(train, evaluation.assign(yes_share=[0.0, 0.0]), extras, ["num"],
                          ["object_legal_form"], "canonical_leaf_plus_effects")
    numeric = first[2]
    pd.testing.assert_frame_equal(first[1][numeric], other[1][numeric])
    assert first[4] == other[4]


def test_unknown_objects_are_explicitly_unannotated():
    train, evaluation, extras = example()
    extras.loc[2, "semantic_tags"] = ""
    extras.loc[2, "semantic_documented"] = 0
    a, b, numeric, _, _, coverage = fold_features(train, evaluation, extras, ["num"],
                                                ["object_legal_form"], "canonical_leaf_plus_effects")
    assert coverage["evaluation_annotated_objects"] == 0
    assert b.semantic_documented.tolist() == [0, 0]
    assert "semantic_documented" in numeric


def test_duplicate_join_is_rejected():
    train, evaluation, extras = example()
    extras = pd.concat([extras, extras.iloc[[0]]], ignore_index=True)
    with pytest.raises(Exception):
        fold_features(train, evaluation, extras, ["num"], ["object_legal_form"], "canonical_leaf")


def test_no_past_annotations_means_exact_baseline_features():
    train, evaluation, extras = example()
    extras.loc[extras.vote_id.isin(["1000", "2000"]), "semantic_tags"] = ""
    extras.loc[extras.vote_id.isin(["1000", "2000"]), "semantic_documented"] = 0
    base = fold_features(train, evaluation, extras, ["num"], ["object_legal_form"], "canonical_leaf")
    enriched = fold_features(train, evaluation, extras, ["num"], ["object_legal_form"], "canonical_leaf_plus_effects")
    assert enriched[2] == base[2]
    assert enriched[3] == base[3]
    pd.testing.assert_frame_equal(base[0], enriched[0])
    pd.testing.assert_frame_equal(base[1], enriched[1])

"""V5 model data contract, temporal protocol, and frequency-filtered features."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.modeling.semantic_training_v5 import VARIANTS, check_plan, fold_features

ROOT = Path(__file__).resolve().parents[1]


def plans():
    v5 = json.loads((ROOT / "experiments/municipal_v5/plan.json").read_text())
    v3 = json.loads((ROOT / "experiments/municipal_v3/plan.json").read_text())
    return v5, v3


def sample():
    def block(ids):
        return pd.DataFrame([
            {
                "vote_id": vote, "municipality_id": municipality,
                "vote_date": "2015-01-01", "yes_share": share,
                "num": 1, "object_domain_1": "4",
                "political_domain_d1e2": "4.2",
            }
            for vote in ids
            for municipality, share in [("a", 0.3), ("b", 0.4)]
        ])
    train = block(["100", "200", "300", "400"])
    eval_frame = block(["500"]).assign(vote_date="2016-01-01")
    extras = pd.DataFrame({
        "vote_id": ["100", "200", "300", "400", "500"],
        "coarse_tags": [
            "mechanism_taxation|direction_increase",
            "mechanism_taxation|direction_increase",
            "mechanism_taxation|direction_increase",
            "mechanism_insurance|domain_welfare",
            "mechanism_future_unknown",
        ],
        "coarse_documented": [1, 1, 1, 1, 0],
        "extra_domain_tokens_1": ["4", "4", "4", "4", "6"],
        "extra_domain_tokens_2": ["4.2", "4.2", "4.2", "4.2", "6.1"],
        "extra_domain_tokens_3": ["4.24", "4.24", "4.24", "4.24", "6.12"],
    })
    return train, eval_frame, extras


def test_v5_is_locked_to_v3_poll_settings_and_dates():
    v5, v3 = plans()
    assert check_plan(v5, v3)
    assert v5["reference_expected_mae_pp"] == pytest.approx(7.618292700184025)
    assert tuple(v5["variants"]) == VARIANTS
    assert v5["mechanism_min_support_in_training_objects"] == 3
    assert v5["frozen_poll_parameters"]["trend_factor"] == 1.0


@pytest.mark.parametrize("field,changed_value", [
    ("training_start", "1981-01-01"),
    ("frozen_poll_parameters", {}),
    ("regressor_parameters", {}),
    ("mechanism_min_support_in_training_objects", 1),
    ("variants", ["baseline_pca5"]),
])
def test_no_silent_parameter_retuning(field, changed_value):
    v5, v3 = plans()
    altered = copy.deepcopy(v5)
    altered[field] = changed_value
    with pytest.raises(ValueError):
        check_plan(altered, v3)


@pytest.mark.parametrize("variant", VARIANTS)
def test_all_variants_preserve_rows_and_only_learn_past(variant):
    train, eval_frame, extras = sample()
    a, b, numeric, categorical, vocab, coverage = fold_features(
        train, eval_frame, extras, ["num"],
        ["object_domain_1", "political_domain_d1e2"], variant, min_support=3,
    )
    assert len(a) == 8 and len(b) == 2
    assert a.vote_id.tolist() == train.vote_id.tolist()
    assert b.vote_id.tolist() == eval_frame.vote_id.tolist()
    assert coverage["train_annotated"] in (0, 4)
    assert len(numeric) + len(categorical) == len(set(numeric + categorical))
    if "coarse_" in variant:
        assert "mechanism_future_unknown" not in vocab["coarse"]
        assert "coarse_mechanism_future_unknown" not in numeric
        assert "coarse_mechanism_taxation" in numeric
        assert b.coarse_mechanism_taxation.eq(0).all()
    if variant == "v3_domain_multihot" or variant.startswith("v3_domains_"):
        assert "object_domain_1" not in categorical
        assert "political_domain_d1e2" not in categorical


def test_future_target_swap_does_not_change_model_features():
    train, evaluation, extras = sample()
    original = fold_features(
        train, evaluation, extras, ["num"],
        ["object_domain_1"], "v3_domains_coarse_all", 3,
    )
    altered = fold_features(
        train, evaluation.assign(yes_share=[0.0, 1.0]), extras,
        ["num"], ["object_domain_1"], "v3_domains_coarse_all", 3,
    )
    pd.testing.assert_frame_equal(
        original[1].drop(columns=["yes_share"]),
        altered[1].drop(columns=["yes_share"]),
    )


def test_missing_semantic_history_is_unknown_not_false():
    train, evaluation, extras = sample()
    extras["coarse_tags"] = ""
    extras["coarse_documented"] = 0
    original = fold_features(train, evaluation, extras, ["num"],
                             ["object_domain_1"], "baseline_pca5", 3)
    variant = fold_features(train, evaluation, extras, ["num"],
                            ["object_domain_1"], "baseline_coarse_all", 3)
    assert original[2] == variant[2] and original[3] == variant[3]
    pd.testing.assert_frame_equal(original[0], variant[0])
    pd.testing.assert_frame_equal(original[1], variant[1])


def test_duplicate_extra_vote_id_causes_join_failure():
    train, evaluation, extras = sample()
    bad = pd.concat([extras, extras.iloc[[0]]], ignore_index=True)
    with pytest.raises(Exception):
        fold_features(train, evaluation, bad, ["num"], [],
                      "baseline_coarse_all", 3)

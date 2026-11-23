"""Matched V3/V4 polling comparison protocol and leakage guards."""

import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.modeling.semantic_poll_comparison_v4 import (
    check_protocol,
    load_expanded_polls,
    paired_date_bootstrap,
    summarize,
)

ROOT = Path(__file__).resolve().parents[1]


def plan():
    v3 = json.loads((ROOT / "experiments/municipal_v3/plan.json").read_text())
    v4 = json.loads((
        ROOT / "experiments/municipal_v4/poll_combination_plan.json"
    ).read_text())
    return v4, v3


def test_v3_parameters_are_exactly_frozen():
    v4, v3 = plan()
    assert check_protocol(v4, v3) is True
    assert v4["reference_expected_mae_pp"] == 7.6183
    assert v4["reference_expected_structural_mae_pp"] == 9.421
    assert v4["frozen_poll_parameters"]["trend_factor"] == 1.0
    assert len(v4["variants"]) == 6


@pytest.mark.parametrize("field,value", [
    ("training_start", "2010-01-01"),
    ("reference", "v3_domain_multihot"),
    ("variants", ["baseline_pca5"]),
    ("frozen_poll_parameters", {}),
    ("regressor_parameters", {}),
])
def test_no_silent_change_of_frozen_comparison(field, value):
    v4, v3 = plan()
    changed = copy.deepcopy(v4)
    changed[field] = value
    with pytest.raises(ValueError):
        check_protocol(changed, v3)


def test_forbidden_comparison_date_is_rejected():
    v4, v3 = plan()
    changed = copy.deepcopy(v4)
    changed["validation_windows"][-1]["end"] = "2023-12-31"
    changed_v3 = copy.deepcopy(v3)
    changed_v3["validation_windows"] = changed["validation_windows"]
    with pytest.raises(ValueError, match="Comparison"):
        check_protocol(changed, changed_v3)


def test_combined_poll_input_refuses_duplicate_vote_wave(tmp_path):
    original = tmp_path / "original.csv"
    historical = tmp_path / "historical.csv"
    a = pd.DataFrame({
        "vote_key": ["A"], "wave": [1], "yes_total": [40],
        "yes_certain": [20], "yes_lean": [20],
        "no_certain": [20], "no_lean": [30],
    })
    a.to_csv(original, index=False)
    b = a.drop(columns=["yes_certain", "yes_lean", "no_certain", "no_lean"])
    b.to_csv(historical, index=False)
    with pytest.raises(ValueError, match="overlap"):
        load_expanded_polls(original, historical)
    b["vote_key"] = "B"
    b.to_csv(historical, index=False)
    combined = load_expanded_polls(original, historical)
    assert len(combined) == 2
    assert "yes_certain" not in combined


def test_subset_mae_still_counts_unpolled_objects():
    frame = pd.DataFrame({
        "vote_id": ["A", "A", "B", "B"],
        "municipality_id": ["x", "y", "x", "y"],
        "vote_date": pd.to_datetime(["2020-01-01"] * 2 + ["2020-02-01"] * 2),
        "yes_share": [0.50] * 4,
        "prediction": [0.50, 0.50, 0.20, 0.20],
        "poll_available": [1.0, 1.0, 0.0, 0.0],
    })
    score, objects, _, sub = summarize(frame)
    assert score["objects"] == 2
    assert score["macro_object_mae_pp"] == pytest.approx(15.0)
    assert len(objects) == 2
    assert sub["polled"]["objects"] == 1
    assert sub["unpolled"]["objects"] == 1
    assert sub["unpolled"]["macro_mae_pp"] == pytest.approx(30.0)
    frame.loc[1, "poll_available"] = 0.0
    with pytest.raises(ValueError, match="Poll coverage"):
        summarize(frame)


def test_date_bootstrap_samples_all_objects_of_each_date():
    rows = []
    for day in range(1, 24):
        for version, mae in [("baseline_pca5", 7.0), ("canonical_leaf", 8.0)]:
            rows.append({
                "vote_id": str(day),
                "vote_date": f"2020-01-{day:02d}",
                "variant": version,
                "mae_pp": mae,
            })
    interval = paired_date_bootstrap(
        pd.DataFrame(rows), "baseline_pca5", "canonical_leaf", repeats=100
    )
    assert interval[0] == pytest.approx(-1.0)
    assert interval[1] == pytest.approx(-1.0)

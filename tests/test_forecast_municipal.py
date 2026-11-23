"""Synthetic future batches: time cutoff, population and absent outcomes."""
import hashlib
import json
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from scripts.integration.build_modeling_dataset import DEMOGRAPHICS
from scripts.modeling import experiment_control_v2 as control
from scripts.modeling import forecast_municipal as forecast_module
from scripts.modeling.forecast_municipal import (
    OUTCOME_COLUMNS,
    build_future_frame,
    load_verified_candidate,
    summarize_forecast,
)


def training():
    return pd.DataFrame([
        ("0001", "6700", "2024-11-24", "VD", .2, np.nan, 0),
        ("0002", "6700", "2024-11-24", "ZH", .7, np.nan, 0),
        ("0003", "6700", "2024-11-24", "GE", .9, np.nan, 0),
        ("0001", "6780", "2025-09-28", "VD", .3, .2, 1),
        ("0002", "6780", "2025-09-28", "ZH", .5, .7, 1),
        ("0001", "6790", "2025-09-28", "VD", .8, .2, 1),
        ("0002", "6790", "2025-09-28", "ZH", .6, .7, 1),
    ], columns=["municipality_id", "vote_id", "vote_date", "canton", "yes_share",
                "history_mean_yes", "history_n_objects"])


def sources():
    swiss = pd.DataFrame({
        "vote_key": ["6900", "6910", "6911", "7000"],
        "vote_date": ["2026-11-29"] * 3 + ["2027-03-07"],
        "rechtsform": [2, 1, 5, 2], "d1e1": ["1"] * 4,
        "d2e1": ["2"] * 4, "d3e1": [None] * 4,
        "titel_off_f": ["Augmentation des impôts", "Réduction des émissions de gaz à effet de serre",
                        "Question subsidiaire", "Un autre objet"],
        "p-sps": [1, 2, 1, 2], "volkja-proz": [99, 1, 99, 1],
    })
    stats = []
    for municipality in ("0001", "0002", "0003"):
        for year, available, population in ((2024, "2025-09-02", 1000),
                                            (2025, "2026-11-25", 9000)):
            row = {"municipality_id": municipality, "year": year, "available_from": available}
            row.update(dict.fromkeys(DEMOGRAPHICS, 0.2))
            row.update(pop_total=population, mean_age=40)
            stats.append(row)
    elections = pd.DataFrame([
        {"municipality_id": municipality, "election_year": year, "party_code": party,
         "party_share": share, "is_special_unit": False}
        for municipality in ("0001", "0002", "0003")
        for year in (2023, 2027)
        for party, share in (("1", .3), ("4", .4))
    ])
    return {
        "swissvotes": swiss, "statpop": pd.DataFrame(stats), "elections": elections,
        "typologies": pd.DataFrame({"municipality_id": ["0001", "0002", "0003"],
                                    "urban_rural": ["urban"] * 3,
                                    "language_region": ["French", "German", "French"]}),
        "ofs": pd.DataFrame({"vote_date": ["2026-11-29"], "votes_yes": [999999]}),
    }


def build(**kwargs):
    return build_future_frame(kwargs.pop("train", training()), kwargs.pop("frames", sources()),
                              kwargs.pop("vote_date", "2026-11-29"),
                              kwargs.pop("as_of", "2026-11-23"), **kwargs)


def test_future_population_is_complete_target_free_and_history_is_past_only():
    train, frames = training(), sources()
    original = train.copy(deep=True)
    result, manifest = build(train=train, frames=frames)
    assert len(result) == 4
    assert set(result.vote_id) == {"6900", "6910"}
    assert set(result.municipality_id) == {"0001", "0002"}
    assert not (OUTCOME_COLUMNS & set(result))
    assert result.feature_cutoff.eq(pd.Timestamp("2026-11-23")).all()
    assert result.vote_date.eq(pd.Timestamp("2026-11-29")).all()
    assert result.history_n_objects.eq(3).all()
    assert result.loc[result.municipality_id.eq("0001"), "history_mean_yes"].eq((.2 + .3 + .8) / 3).all()
    np.testing.assert_allclose(result.loc[result.municipality_id.eq("0002"), "history_mean_yes"], .6)
    assert manifest["excluded_subsidiary_objects"] == 1
    assert manifest["current_ofs_outcomes_read"] is False
    assert manifest["future_outcome_columns"] == []
    pd.testing.assert_frame_equal(train, original)


def test_asof_joins_exclude_releases_between_capture_and_future_vote():
    result, _ = build()
    assert result.statpop_pop_total.eq(1000).all()
    assert result.statpop_year.eq(2024).all()
    assert result.election_year.eq(2023).all()
    assert result.statpop_selection_from.le(result.feature_cutoff).all()
    assert result.election_selection_from.le(result.feature_cutoff).all()
    # Even a later requested cutoff cannot read the future vote outcome.
    later, _ = build(as_of="2026-11-26")
    assert later.statpop_pop_total.eq(9000).all()
    assert not (OUTCOME_COLUMNS & set(later))


def test_current_source_outcomes_cannot_change_future_features_or_manifest():
    frames = sources()
    expected, expected_manifest = build(frames=frames)
    frames["ofs"] = object()  # No attribute on this input may be read.
    frames["swissvotes"]["volkja-proz"] = [1, 99, 1, 99]
    frames["swissvotes"]["yes_share"] = np.nan
    actual, actual_manifest = build(frames=frames)
    pd.testing.assert_frame_equal(expected, actual)
    assert expected_manifest == actual_manifest


@pytest.mark.parametrize("vote_date,as_of", [
    ("2026-11-29", "2026-11-29"),
    ("2026-11-29", "2026-12-01"),
    ("2026-11-29", "2025-09-28"),
])
def test_invalid_temporal_admission_is_rejected(vote_date, as_of):
    with pytest.raises(ValueError, match="strictly"):
        build(vote_date=vote_date, as_of=as_of)


def test_future_training_results_and_inconsistent_history_are_rejected():
    train = training()
    train.loc[train.vote_id.eq("6790"), "vote_date"] = "2026-11-24"
    with pytest.raises(ValueError, match="strictly precede"):
        build(train=train)
    train = training()
    train.loc[train.vote_id.eq("6790"), "history_n_objects"] = 2
    with pytest.raises(ValueError, match="Same-date"):
        build(train=train)


def test_exact_future_date_and_unique_object_keys_are_required():
    with pytest.raises(ValueError, match="No Swissvotes"):
        build(vote_date="2026-12-06")
    frames = sources()
    frames["swissvotes"] = pd.concat([frames["swissvotes"], frames["swissvotes"].iloc[:1]])
    with pytest.raises(ValueError, match="duplicate"):
        build(frames=frames)


def test_optional_poll_adapter_receives_target_free_frame_and_actual_cutoff(monkeypatch):
    calls = []

    def add_poll_features(frame, polls, as_of):
        assert not (OUTCOME_COLUMNS & set(frame))
        calls.append((polls, as_of))
        return frame.assign(poll_yes_share=.55, poll_population_weight=400), {"status": "fixture"}

    monkeypatch.setitem(sys.modules, "scripts.modeling.poll_anchor",
                        SimpleNamespace(add_poll_features=add_poll_features))
    frames = sources()
    frames["polls"] = pd.DataFrame({"fixture": [1]})
    result, manifest = build(frames=frames)
    assert calls[0][1] == pd.Timestamp("2026-11-23")
    assert calls[0][0] is frames["polls"]
    assert result.poll_yes_share.eq(.55).all()
    assert manifest["polls"]["status"] == "fixture"


def test_summary_separates_unweighted_mean_and_explicit_proxy():
    future, _ = build()
    future = future.loc[future.vote_id.eq("6900")].copy()
    future["poll_population_weight"] = [1., 3.]
    row = summarize_forecast(future, [.2, .8]).iloc[0]
    assert row.mean_yes_share_unweighted == .5
    assert row.weighted_yes_share_proxy == pytest.approx(.65)
    assert row.weight_column == "poll_population_weight"
    assert "excludes age 18-19" in row.weight_definition
    future["poll_population_weight"] = [np.nan, 0.]
    row = summarize_forecast(future, [.2, .8]).iloc[0]
    assert pd.isna(row.weighted_yes_share_proxy)
    assert row.weight_coverage_share == 0
    with pytest.raises(ValueError, match="proportions"):
        summarize_forecast(future, [.2, 1.5])


def frozen_candidate(tmp_path):
    """Small authentic freeze signature; no model is trained or forecast made."""
    model_path = tmp_path / "candidate_model.joblib"
    model_path.write_bytes(b"model bytes, never deserialized by these tests")
    manifest_path = tmp_path / "data_manifest.json"
    manifest_path.write_text("{}")
    frozen = {
        "data_sha256": "fixture-dataset", "code": {"model.py": "frozen-code"},
        "environment": {"python": "fixture-version"},
        "data_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    }
    frozen["signature"] = hashlib.sha256(json.dumps(frozen, sort_keys=True, default=str).encode()).hexdigest()
    (tmp_path / "frozen_selection.json").write_text(json.dumps(frozen))
    card = {"model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
            "frozen_signature": frozen["signature"], "environment": frozen["environment"],
            "training_start": "2024-11-24", "training_end": "2025-09-28"}
    (tmp_path / "candidate_model_card.json").write_text(json.dumps(card))
    return frozen, card


@pytest.mark.parametrize("changed", ["code", "environment"])
def test_frozen_implementation_or_environment_drift_blocks_deserialization(tmp_path, monkeypatch, changed):
    frozen, _ = frozen_candidate(tmp_path)
    monkeypatch.setattr(control, "read_data", lambda output: (training(), {"dataset_sha256": "fixture-dataset"}))
    monkeypatch.setattr(control, "code_hashes", lambda: {"model.py": "new-code"} if changed == "code" else frozen["code"])
    monkeypatch.setattr(control, "environment", lambda: {"python": "new-version"} if changed == "environment" else frozen["environment"])
    loads = []
    monkeypatch.setattr(forecast_module.joblib, "load", lambda path: loads.append(path))
    with pytest.raises(ValueError, match="Frozen (code or data|environment) changed"):
        load_verified_candidate(tmp_path)
    assert loads == []


def test_card_requires_the_same_frozen_signature_before_deserialization(tmp_path, monkeypatch):
    frozen, card = frozen_candidate(tmp_path)
    card["frozen_signature"] = "some-other-selection"
    (tmp_path / "candidate_model_card.json").write_text(json.dumps(card))
    monkeypatch.setattr(forecast_module, "verify_freeze", lambda output: (frozen, training(), {}))
    loads = []
    monkeypatch.setattr(forecast_module.joblib, "load", lambda path: loads.append(path))
    with pytest.raises(ValueError, match="frozen selection signature"):
        load_verified_candidate(tmp_path)
    assert loads == []


def test_verified_candidate_reuses_validated_history_before_loading(tmp_path, monkeypatch):
    frozen, card = frozen_candidate(tmp_path)
    events = []

    def verify(output):
        events.append("verify")
        return frozen, training(), {}

    model = object()

    def load(path):
        assert events == ["verify"]
        events.append("load")
        return model

    monkeypatch.setattr(forecast_module, "verify_freeze", verify)
    monkeypatch.setattr(forecast_module.joblib, "load", load)
    loaded, history, observed_card, observed_frozen = load_verified_candidate(tmp_path)
    assert loaded is model
    assert len(history) == len(training())
    assert observed_card == card
    assert observed_frozen == frozen
    assert events == ["verify", "load"]

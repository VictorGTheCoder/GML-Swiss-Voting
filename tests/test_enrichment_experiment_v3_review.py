"""Independent checks of the experimental fold and cached prediction boundary."""

import json

import numpy as np
import pandas as pd
import pytest

from scripts.modeling import enrichment_experiment_v3 as experiment
from scripts.modeling.enrichment_experiment_v3 import CachedPredictionModel, assemble_fold


def test_fold_vocabulary_and_predictors_ignore_future_domains_and_targets():
    train = pd.DataFrame({"vote_id": ["old", "old"], "municipality_id": ["a", "b"],
                          "yes_share": [.1, .2]})
    evaluation = pd.DataFrame({"vote_id": ["new", "new"], "municipality_id": ["a", "b"],
                               "yes_share": [.3, .4]})
    manifest = {"political": {"object_numeric_features": [], "object_categorical_features": []}}
    extras = pd.DataFrame({
        "vote_id": ["old", "new", "later"],
        "extra_domain_tokens_1": ["1", "1|2", "9"],
        "extra_domain_tokens_2": ["1.1", "2.1", "9.1"],
        "extra_domain_tokens_3": ["1.11", "", "9.11"],
    })
    configuration = {"groups": [], "domain_multihot": True}
    a, b, numeric, categorical, vocabulary = assemble_fold(
        train, evaluation, manifest, extras, {}, configuration)
    assert vocabulary == {
        "extra_domain_tokens_1": ["1"], "extra_domain_tokens_2": ["1.1"],
        "extra_domain_tokens_3": ["1.11"],
    }
    assert len(a) == len(train) and len(b) == len(evaluation)
    assert all("9" not in name for name in numeric)
    assert "extra_domain_present_2_2_1" not in numeric
    assert b.extra_domain_present_1_1.tolist() == [1., 1.]
    assert b.extra_domain_present_2_1_1.tolist() == [0., 0.]
    changed = evaluation.assign(yes_share=[.99, .01])
    _, b_changed, numeric_changed, categories_changed, vocabulary_changed = assemble_fold(
        train, changed, manifest, extras, {}, configuration)
    pd.testing.assert_frame_equal(b[numeric], b_changed[numeric_changed])
    assert categorical == categories_changed and vocabulary == vocabulary_changed
    assert "yes_share" not in numeric + categorical


def test_cached_prediction_order_depends_only_on_keys_and_rejects_missing_keys():
    stored = pd.DataFrame({"municipality_id": ["a", "b"], "vote_id": ["v", "v"],
                           "prediction": [.25, .75], "yes_share": [1., 0.]})
    model = CachedPredictionModel(stored)
    request = pd.DataFrame({"municipality_id": ["b", "a"], "vote_id": ["v", "v"],
                            "yes_share": [.7, .9]})
    np.testing.assert_array_equal(model.predict(request), [.75, .25])
    np.testing.assert_array_equal(model.predict(request.drop(columns="yes_share")), [.75, .25])
    with pytest.raises(ValueError, match="Missing cached"):
        model.predict(request.assign(vote_id="unseen"))


def test_enrichment_join_rejects_duplicate_object_rows():
    frame = pd.DataFrame({"vote_id": ["a"], "municipality_id": ["c"]})
    extras = pd.DataFrame({"vote_id": ["a", "a"], "extra_numeric": [1., 2.]})
    manifest = {"political": {"object_numeric_features": [], "object_categorical_features": []}}
    extra_manifest = {"groups": {"new": {"numeric": ["extra_numeric"], "categorical": []}}}
    with pytest.raises(pd.errors.MergeError):
        assemble_fold(frame, frame, manifest, extras, extra_manifest, {"groups": ["new"]})


def _campaign_fixture(tmp_path, monkeypatch):
    """Minimal files sufficient to exercise guards before any estimator runs."""
    inputs, campaign_dir = tmp_path / "input", tmp_path / "campaign"
    inputs.mkdir()
    campaign_dir.mkdir()
    original_polls = tmp_path / "data/external/polls/srg_gfs_polls.csv"
    original_polls.parent.mkdir(parents=True)
    original_polls.write_text("vote_key,wave,yes_certain,yes_lean,no_certain,no_lean\n1,1,10,20,30,40\n")
    historical = tmp_path / "history.csv"
    historical.write_text("vote_key,wave\n2,1\n")
    (inputs / "dataset.parquet").write_bytes(b"dataset contents before modification")
    (inputs / "data_manifest.json").write_text("{}")
    prediction_file = campaign_dir / "baseline_pca5_predictions.parquet"
    prediction_file.write_bytes(b"cached predictions before modification")
    evidence = {
        "status": "complete", "dataset_sha256": experiment.sha(inputs / "dataset.parquet"),
        "code": {"module.py": "fixed-source"},
        "base_manifest_sha256": experiment.sha(inputs / "data_manifest.json"),
        "original_polls_sha256": experiment.sha(original_polls),
        "plan": {"polling_variants": [{"structure": "baseline_pca5", "collection": "original"}]},
        "runs": [{"name": "baseline_pca5", "predictions_sha256": experiment.sha(prediction_file)}],
    }
    (campaign_dir / "campaign.json").write_text(json.dumps(evidence))
    monkeypatch.setattr(experiment, "ROOT", tmp_path)
    monkeypatch.setattr(experiment, "_code_evidence", lambda: {"module.py": "fixed-source"})
    return inputs, campaign_dir, original_polls, historical, prediction_file


@pytest.mark.parametrize("changed, message", [
    ("dataset", "Base dataset changed"),
    ("manifest", "Base manifest changed"),
    ("polls", "Original poll collection changed"),
    ("code", "Model implementation changed"),
])
def test_poll_reuse_rejects_mixed_provenance_before_reading_sources(tmp_path, monkeypatch, changed, message):
    inputs, campaign_dir, original_polls, historical, _ = _campaign_fixture(tmp_path, monkeypatch)
    if changed == "code":
        monkeypatch.setattr(experiment, "_code_evidence", lambda: {"module.py": "changed-source"})
    else:
        path = {"dataset": inputs / "dataset.parquet", "manifest": inputs / "data_manifest.json",
                "polls": original_polls}[changed]
        path.write_bytes(b"changed after structural campaign")

    def unexpected_read(*args, **kwargs):
        raise AssertionError("No data parsing should occur after a failed provenance guard")

    monkeypatch.setattr(pd, "read_csv", unexpected_read)
    monkeypatch.setattr(pd, "read_parquet", unexpected_read)
    with pytest.raises(ValueError, match=message):
        experiment.polling_comparison(inputs, campaign_dir, historical, tmp_path / "output")


def test_poll_reuse_rejects_modified_prediction_cache_before_loading_it(tmp_path, monkeypatch):
    inputs, campaign_dir, _, historical, prediction_file = _campaign_fixture(tmp_path, monkeypatch)
    prediction_file.write_bytes(b"modified prediction values")
    reads = []

    def input_only_read(path, **kwargs):
        reads.append(path)
        assert path == inputs / "dataset.parquet", "A modified prediction cache must not be loaded"
        return pd.DataFrame({"vote_id": ["1"]})

    monkeypatch.setattr(pd, "read_parquet", input_only_read)
    monkeypatch.setattr(experiment, "add_poll_features", lambda frame, polls: (frame, {}))
    with pytest.raises(ValueError, match="Cached structural predictions changed"):
        experiment.polling_comparison(inputs, campaign_dir, historical, tmp_path / "output")
    assert reads == [inputs / "dataset.parquet"]


@pytest.mark.parametrize("plan, message", [
    ({"training_start": "2000-01-01"}, "requires the V2 training start"),
    ({"training_start": "1990-01-01", "validation_windows": [{"end": "2023-01-01"}]},
     "must end before 2023"),
])
def test_campaign_rejects_changed_temporal_contract_before_loading_data(tmp_path, plan, message):
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match=message):
        experiment.run(tmp_path / "missing_input", tmp_path / "missing_extras", tmp_path / "output", plan_path)

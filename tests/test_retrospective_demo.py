"""Observable contracts of the recovered retrospective experiment."""
import json

import numpy as np
import pandas as pd
import pytest

from scripts.modeling import retrospective_demo as demo


def test_history_excludes_same_date_and_all_heldout_targets():
    outcomes = pd.DataFrame({'municipality_id': ['0001'] * 5,
        'vote_date': pd.to_datetime(['2011-01-01', '2020-01-01', '2020-01-01', '2021-01-01', '2023-01-01']),
        'yes_share': [.2, .4, .8, .9, 1.]})
    targets = pd.DataFrame({'municipality_id': ['0001', '0001', '0001', '0002'],
        'vote_date': pd.to_datetime(['2020-01-01', '2021-01-01', '2022-01-01', '2022-01-01'])})
    before = demo.frozen_history(targets, outcomes)
    np.testing.assert_allclose(before.history_mean_yes, [.2, 1.4 / 3, 1.4 / 3, np.nan], equal_nan=True)
    outcomes.loc[outcomes.vote_date.gt(demo.TRAIN_END), 'yes_share'] = 0
    pd.testing.assert_frame_equal(before, demo.frozen_history(targets, outcomes))


def test_complete_demo_exports_paired_validation_and_reloadable_model(tmp_path, monkeypatch):
    data = pd.DataFrame({c: [0.2, .6, .4, .8] for c in demo.NUMERIC + demo.INDICATORS})
    for c in demo.CATEGORICAL:
        data[c] = ['known', 'known', 'unseen', None]
    data['party_share_centre'] = [np.nan, np.nan, .5, .7]
    data['municipality_id'] = ['0001', '0002', '0001', '0002']
    data['vote_id'] = ['train', 'train', 'validation', 'validation']
    data['vote_date'] = pd.to_datetime(['2020-01-01'] * 2 + ['2021-01-01'] * 2)
    data['yes_share'] = [.2, .6, .9, .3]
    data['partition'] = ['train'] * 2 + ['validation'] * 2
    manifest = {'sources': {}, 'blocks': {}, 'exclusions_sequential': []}
    monkeypatch.setattr(demo, 'load_inputs', lambda root: (data, manifest, []))
    # Keep provenance inputs present; the loader itself is deliberately replaced by the synthetic prepared seam.
    folder = tmp_path / 'data/processed/modeling'
    folder.mkdir(parents=True)
    (folder / 'municipal_structured.parquet').write_bytes(b'synthetic')
    (folder / 'manifest.json').write_text('{}')
    output = tmp_path / 'run'
    predictions, scores, run_manifest = demo.run(tmp_path, output)
    assert set(predictions.vote_id) == {'validation'}
    assert predictions.groupby('model').size().eq(2).all()
    assert len(scores) == 5
    assert predictions.prediction.between(0, 1).all()
    assert run_manifest['artifact_reload_predictions_identical']
    assert run_manifest['excluded_all_missing_training_features'] == ['party_share_centre']
    loaded = demo.joblib.load(output / 'boosting.joblib')['pipeline']
    encoder = loaded.named_steps['prepare'].named_transformers_['categorical']
    assert all(categories.tolist() == ['known'] for categories in encoder.categories_)
    assert run_manifest['test_evaluated'] is False
    assert (output / 'prediction_examples.svg').exists()
    assert set(pd.read_parquet(output / 'validation_predictions.parquet').vote_id) == {'validation'}
    assert json.loads((output / 'run_manifest.json').read_text())['artifact_sha256'] == demo.sha256(output / 'boosting.joblib')
    # Validation labels affect scores, but cannot change fitted predictions/preprocessing.
    data.loc[data.partition.eq('validation'), 'yes_share'] = [0, 1]
    second, _, _ = demo.run(tmp_path, tmp_path / 'second', include_ridge=False)
    np.testing.assert_array_equal(
        predictions.loc[predictions.model.eq('hist_gradient_boosting'), 'raw_prediction'],
        second.loc[second.model.eq('hist_gradient_boosting'), 'raw_prediction'])


def test_modified_source_fails_closed(tmp_path):
    folder = tmp_path / 'data/processed/modeling'
    folder.mkdir(parents=True)
    source = tmp_path / 'source.parquet'
    source.write_bytes(b'changed')
    manifest = {'mode': 'exploratory_retrospective', 'strict_forecast_ready': False,
                'numeric_features': demo.NUMERIC, 'categorical_features': demo.CATEGORICAL,
                'missing_indicators': demo.INDICATORS, 'target': 'yes_share',
                'sources': {'ofs': {'path': 'source.parquet', 'sha256': 'wrong'}}}
    (folder / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='Source changed'):
        demo.load_inputs(tmp_path)


def test_loader_filters_reserved_targets_before_reading(tmp_path, monkeypatch):
    from scripts.integration.build_modeling_dataset import FLAGS

    directory = tmp_path / 'data/processed/modeling'
    directory.mkdir(parents=True)
    source = pd.DataFrame({'municipality_id': ['0001'] * 4, 'vote_id': ['old', 'train', 'val', 'test'],
        'vote_date': pd.to_datetime(['2010-01-01', '2020-01-01', '2021-01-01', '2023-01-01']),
        'votes_yes': [20, 60, 80, -999], 'votes_no': [80, 40, 20, -999], **dict.fromkeys(FLAGS, False)})
    source.to_parquet(tmp_path / 'source.parquet')
    data = source.iloc[1:][['municipality_id', 'vote_id', 'vote_date']].copy()
    for c in demo.NUMERIC + demo.INDICATORS:
        data[c] = .2
    for c in demo.CATEGORICAL:
        data[c] = 'category'
    data['yes_share'] = [.6, .8, -999]
    data['geography_id'] = 'retrospective_fixed_2026-01-01'
    data['strict_forecast_ready'] = False
    data['statpop_selection_from'] = pd.Timestamp('2019-01-01')
    data['election_selection_from'] = pd.Timestamp('2019-01-01')
    dataset = directory / 'municipal_structured.parquet'
    data.to_parquet(dataset)
    manifest = {'mode': 'exploratory_retrospective', 'strict_forecast_ready': False,
                'numeric_features': demo.NUMERIC, 'categorical_features': demo.CATEGORICAL,
                'missing_indicators': demo.INDICATORS, 'target': 'yes_share',
                'sources': {'ofs': {'path': 'source.parquet', 'sha256': demo.sha256(tmp_path / 'source.parquet')}}}
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(demo, 'DATASET_SHA256', demo.sha256(dataset))
    read = pd.read_parquet
    calls = []
    def tracked_read(path, **kwargs):
        calls.append(kwargs.get('filters'))
        return read(path, **kwargs)
    monkeypatch.setattr(pd, 'read_parquet', tracked_read)
    loaded, _, _ = demo.load_inputs(tmp_path)
    assert set(loaded.vote_id) == {'train', 'val'}
    assert calls == [[('vote_date', '<=', demo.VALIDATION_END)], [('vote_date', '<=', demo.TRAIN_END)]]
    assert loaded.loc[loaded.partition.eq('validation'), 'history_mean_yes'].iloc[0] == pytest.approx(.4)

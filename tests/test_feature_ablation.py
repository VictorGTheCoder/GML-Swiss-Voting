"""Temporal isolation and paired-observation contracts for the ablation."""
import json

import numpy as np
import pandas as pd
import pytest

from scripts.modeling import feature_ablation as ablation


def fixture():
    data = pd.DataFrame({c: [.1, .5, .3, .7] for c in ablation.NUMERIC + ablation.INDICATORS})
    for c in ablation.CATEGORICAL:
        data[c] = ['known', 'known', 'unseen', np.nan]
    data['party_share_centre'] = [np.nan, np.nan, .3, .4]
    data['municipality_id'] = ['0001', '0002', '0001', '0002']
    data['vote_id'] = ['a', 'a', 'b', 'b']
    data['vote_date'] = pd.to_datetime(['2020-01-01'] * 2 + ['2021-01-01'] * 2)
    data['yes_share'] = [.2, .6, .9, .3]
    data['partition'] = ['train', 'train', 'validation', 'validation']
    return data


def test_paired_rows_and_heldout_labels_do_not_change_predictions():
    data = fixture()
    first, scores, configs = ablation.compare(data)
    assert first.groupby('model').size().eq(2).all()
    keys = first[['municipality_id', 'vote_id']].drop_duplicates()
    assert len(keys) == 2
    assert scores.rows.eq(2).all()
    assert configs['D']['all_missing_training'] == ['party_share_centre']
    assert scores.gain_vs_A_pp.iloc[0] == 0
    data.loc[data.partition.eq('validation'), 'yes_share'] = [0, 1]
    second, _, _ = ablation.compare(data)
    np.testing.assert_array_equal(first.raw_prediction, second.raw_prediction)


def test_train_only_encoding_scaling_and_imputation():
    data = fixture()
    model = ablation.ridge_pipeline(['history_mean_yes'], ['language_region'], 1.)
    model.fit(data.iloc[:2], data.yes_share.iloc[:2])
    prepare = model.named_steps['prepare']
    assert prepare.named_transformers_['categorical'].named_steps['encode'].categories_[0].tolist() == ['known']
    numeric = prepare.named_transformers_['numeric']
    assert numeric.named_steps['impute'].statistics_[0] == pytest.approx(.3)
    assert numeric.named_steps['scale'].mean_[0] == pytest.approx(.3)
    assert np.isfinite(model.predict(data.iloc[2:])).all()


def test_wrong_partition_or_reserved_date_is_rejected():
    data = fixture()
    data.loc[2, 'partition'] = 'train'
    with pytest.raises(ValueError, match='Partitions'):
        ablation.compare(data)
    data = fixture()
    data.loc[2, 'vote_date'] = pd.Timestamp('2023-01-01')
    with pytest.raises(ValueError, match='Only training'):
        ablation.compare(data)


def test_history_excludes_same_day_and_heldout_targets():
    outcomes = pd.DataFrame({'municipality_id': ['0001'] * 5,
        'vote_date': pd.to_datetime(['2011-01-01', '2020-01-01', '2020-01-01', '2021-01-01', '2023-01-01']),
        'yes_share': [.2, .4, .8, .9, 1.]})
    targets = outcomes.iloc[[1, 3, 4]][['municipality_id', 'vote_date']]
    before = ablation.frozen_history(targets, outcomes)
    np.testing.assert_allclose(before.history_mean_yes, [.2, 1.4 / 3, 1.4 / 3])
    outcomes.loc[outcomes.vote_date.gt(ablation.TRAIN_END), 'yes_share'] = 0
    pd.testing.assert_frame_equal(before, ablation.frozen_history(targets, outcomes))


def test_loader_filters_reserved_targets_before_reading(tmp_path, monkeypatch):
    from scripts.integration.build_modeling_dataset import FLAGS

    directory = tmp_path / 'data/processed/modeling'
    directory.mkdir(parents=True)
    source = pd.DataFrame({'municipality_id': ['0001'] * 4, 'vote_id': ['old', 'train', 'val', 'test'],
        'vote_date': pd.to_datetime(['2010-01-01', '2020-01-01', '2021-01-01', '2023-01-01']),
        'votes_yes': [20, 60, 80, -999], 'votes_no': [80, 40, 20, -999], **dict.fromkeys(FLAGS, False)})
    source.to_parquet(tmp_path / 'source.parquet')
    data = source.iloc[1:][['municipality_id', 'vote_id', 'vote_date']].copy()
    for c in ablation.NUMERIC + ablation.INDICATORS:
        data[c] = .2
    for c in ablation.CATEGORICAL:
        data[c] = 'category'
    data['yes_share'] = [.6, .8, -999]
    data['geography_id'] = 'retrospective_fixed_2026-01-01'
    data['strict_forecast_ready'] = False
    data['statpop_selection_from'] = pd.Timestamp('2019-01-01')
    data['election_selection_from'] = pd.Timestamp('2019-01-01')
    dataset = directory / 'municipal_structured.parquet'
    data.to_parquet(dataset)
    manifest = {'mode': 'exploratory_retrospective', 'strict_forecast_ready': False,
                'numeric_features': ablation.NUMERIC, 'categorical_features': ablation.CATEGORICAL,
                'missing_indicators': ablation.INDICATORS, 'target': 'yes_share',
                'sources': {'ofs': {'path': 'source.parquet', 'sha256': ablation.sha256(tmp_path / 'source.parquet')}}}
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(ablation, 'DATASET_SHA256', ablation.sha256(dataset))
    read = pd.read_parquet
    calls = []
    def tracked_read(path, **kwargs):
        calls.append(kwargs.get('filters'))
        return read(path, **kwargs)
    monkeypatch.setattr(pd, 'read_parquet', tracked_read)
    loaded, _, _ = ablation.load_inputs(tmp_path)
    assert set(loaded.vote_id) == {'train', 'val'}
    assert calls == [[('vote_date', '<=', ablation.VALIDATION_END)], [('vote_date', '<=', ablation.TRAIN_END)]]
    assert loaded.loc[loaded.partition.eq('validation'), 'history_mean_yes'].iloc[0] == pytest.approx(.4)

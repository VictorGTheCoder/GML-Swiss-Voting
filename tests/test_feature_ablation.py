"""Temporal isolation and paired-observation contracts for the ablation."""
import numpy as np
import pandas as pd
import pytest

from scripts.modeling import feature_ablation as ablation


def fixture():
    data = pd.DataFrame({c: [.1, .5, .3, .7] for c in [c for num, _ in ablation.GROUPS.values() for c in num]})
    for c in [c for _, cat in ablation.GROUPS.values() for c in cat]:
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

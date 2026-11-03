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


def test_every_singleton_and_pair_uses_identical_validation_keys():
    from itertools import combinations

    data = fixture()
    predictions, scores, configs = ablation.compare(data)
    expected = {groups for size in [1, 2] for groups in combinations(ablation.GROUPS, size)}
    observed = {tuple(config['groups']) for config in configs.values() if len(config['groups']) <= 2}
    assert observed == expected
    assert len(configs) == 18  # A and B already represent one singleton and one pair.
    assert scores.n_groups.le(2).sum() == 15
    assert scores.loc[~scores.configuration.isin(list('ABCDE')), 'gain_vs_previous_pp'].isna().all()
    keys = data.loc[data.partition.eq('validation'), ['municipality_id', 'vote_id', 'vote_date']].reset_index(drop=True)
    for _, frame in predictions.groupby('model'):
        pd.testing.assert_frame_equal(frame[keys.columns].reset_index(drop=True), keys)


def test_objects_only_does_not_use_communal_history_or_other_groups():
    data = fixture()
    # Equal object metadata across communes, very different municipal inputs.
    for column in ablation.GROUPS['objets'][1]:
        data.loc[data.partition.eq('validation'), column] = 'known'
    first, _, configs = ablation.compare(data)
    name = next(name for name, config in configs.items() if config['groups'] == ['objets'])
    assert configs[name]['numeric'] == []
    assert configs[name]['categorical'] == ablation.GROUPS['objets'][1]
    raw = first.loc[first.model.eq(name), 'raw_prediction'].to_numpy()
    assert raw[0] == pytest.approx(raw[1])
    # Perturb all communal groups in both periods, keeping objects and targets fixed.
    for group, (numeric, categorical) in ablation.GROUPS.items():
        if group == 'objets':
            continue
        for column in numeric:
            data[column] = [2., 20., 200., 2000.]
        for column in categorical:
            data[column] = ['new1', 'new2', 'new3', 'new4']
    second, _, _ = ablation.compare(data)
    np.testing.assert_array_equal(raw, second.loc[second.model.eq(name), 'raw_prediction'])

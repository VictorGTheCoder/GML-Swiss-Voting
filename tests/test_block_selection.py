"""Chronological leakage and paired block utility contracts."""
import numpy as np
import pandas as pd
import pytest

from scripts.modeling import block_selection as selection
from scripts.modeling import retrospective_demo as demo


def sample_data():
    rng = np.random.default_rng(41)
    data = pd.DataFrame({c: rng.uniform(size=12) for c in demo.NUMERIC + demo.INDICATORS})
    for column in demo.CATEGORICAL:
        data[column] = ['known'] * 4 + ['new'] * 8
    data['municipality_id'] = ['0001', '0002'] * 6
    data['vote_id'] = np.repeat(['a', 'b', 'c', 'd', 'e', 'f'], 2)
    data['vote_date'] = pd.to_datetime(np.repeat(
        ['2014-03-01', '2014-06-01', '2016-03-01', '2016-06-01', '2017-03-01', '2017-06-01'], 2))
    data['yes_share'] = rng.uniform(size=12)
    outcomes = data[['municipality_id', 'vote_date', 'yes_share']].copy()
    return data, outcomes


def test_heldout_labels_and_precomputed_history_cannot_change_window_predictions():
    data, outcomes = sample_data()
    _, train, evaluation = next(selection.chronological_windows(data, (2016,)))
    first, _ = selection.fit_window(train, evaluation, outcomes)
    # Corrupt all evaluation outcomes, including those that precede another evaluation date.
    outcomes.loc[outcomes.vote_date.dt.year.ge(2016), 'yes_share'] = 1
    evaluation['yes_share'] = 0
    train[selection.HISTORY] = 999
    evaluation[selection.HISTORY] = -999
    second, _ = selection.fit_window(train, evaluation, outcomes)
    np.testing.assert_array_equal(first.raw_prediction, second.raw_prediction)
    assert not first.target_share.equals(second.target_share)
    expected = evaluation[['municipality_id', 'vote_id', 'vote_date']].reset_index(drop=True)
    for _, group in first.groupby('model'):
        pd.testing.assert_frame_equal(group[expected.columns].reset_index(drop=True), expected)
    assert first.prediction.between(0, 1).all()


def test_window_history_excludes_same_day_and_stays_frozen():
    _, outcomes = sample_data()
    targets = pd.DataFrame({'municipality_id': ['0001'] * 3,
                            'vote_date': pd.to_datetime(['2014-06-01', '2016-03-01', '2016-06-01'])})
    history = demo.frozen_history(targets, outcomes, train_end=pd.Timestamp('2014-06-01'))
    prior = outcomes.loc[outcomes.municipality_id.eq('0001') & outcomes.vote_date.dt.year.eq(2014)]
    np.testing.assert_allclose(history.history_mean_yes, [prior.yes_share.iloc[0], prior.yes_share.mean(),
                                                        prior.yes_share.mean()])
    assert history.history_n_objects.tolist() == [1, 2, 2]


def test_expanding_windows_preserve_whole_dates_and_reject_exposed_validation():
    data, outcomes = sample_data()
    windows = list(selection.chronological_windows(data, (2016, 2017)))
    assert len(windows[1][1]) > len(windows[0][1])
    for _, train, evaluation in windows:
        assert train.vote_date.max() < evaluation.vote_date.min()
        assert set(train.vote_id).isdisjoint(evaluation.vote_id)
    data.loc[0, 'vote_date'] = pd.Timestamp('2021-01-01')
    with pytest.raises(ValueError, match='2012–2020'):
        list(selection.chronological_windows(data))


def test_gain_signs_match_block_utility_and_compare_identical_units():
    rows = [{'window': 2016, 'model': 'history', 'mae_pp': 10},
            {'window': 2016, 'model': 'combined', 'mae_pp': 6}]
    for block in selection.block_features():
        rows += [{'window': 2016, 'model': f'add_{block}', 'mae_pp': 8},
                 {'window': 2016, 'model': f'remove_{block}', 'mae_pp': 9}]
    table = pd.DataFrame(rows)
    gains = selection.paired_gains(table, ['window'], 'mae_pp')
    assert gains.loc[gains.operation.eq('add'), 'gain_pp'].eq(2).all()
    assert gains.loc[gains.operation.eq('remove'), 'gain_pp'].eq(3).all()
    table.loc[table.model.eq('remove_object'), 'window'] = 2017
    with pytest.raises(ValueError, match='identical evaluation units'):
        selection.paired_gains(table, ['window'], 'mae_pp')

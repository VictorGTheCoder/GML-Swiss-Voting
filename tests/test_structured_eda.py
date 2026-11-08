"""Guard train-only fitting and paired evaluation of retrospective block comparisons."""
import numpy as np
import pandas as pd
import pytest

from scripts.modeling import retrospective_demo as demo
from scripts.modeling import structured_eda as eda


def sample_frames():
    rng = np.random.default_rng(42)
    frame = pd.DataFrame({c: rng.uniform(size=12) for c in demo.NUMERIC + demo.INDICATORS})
    for column in demo.CATEGORICAL:
        frame[column] = ['a', 'b'] * 4 + ['unseen'] * 4
    frame['party_share_centre'] = [np.nan] * 8 + [.9] * 4
    frame['yes_share'] = rng.uniform(size=12)
    frame['municipality_id'] = ['0001', '0002'] * 6
    frame['vote_id'] = np.repeat(['t1', 't2', 't3', 't4', 'v1', 'v2'], 2)
    frame['vote_date'] = pd.to_datetime(['2020-01-01'] * 8 + ['2021-01-01'] * 4)
    return frame.iloc[:8].copy(), frame.iloc[8:].copy()


def test_block_fits_ignore_validation_targets_and_preserve_paired_keys():
    train, validation = sample_frames()
    fits, predictions, scores, objects, dates = eda.fit_comparisons(train, validation)
    changed = validation.copy()
    changed['yes_share'] = 1 - changed.yes_share
    fits2, predictions2, scores2, _, _ = eda.fit_comparisons(train, changed)
    np.testing.assert_array_equal(predictions.raw_prediction, predictions2.raw_prediction)
    assert not scores.mae_pp.equals(scores2.mae_pp)
    pd.testing.assert_frame_equal(eda.coefficient_table(fits['ridge_combined']),
                                  eda.coefficient_table(fits2['ridge_combined']))
    keys = ['municipality_id', 'vote_id', 'vote_date']
    for _, group in predictions.groupby('model'):
        pd.testing.assert_frame_equal(group[keys].reset_index(drop=True), validation[keys].reset_index(drop=True))
    encoder = fits['ridge_combined'].named_steps['prepare'].named_transformers_['categorical']['encode']
    assert all('unseen' not in levels for levels in encoder.categories_)
    # Validation has values for this predictor; training has none. Fit must retain training-only zero imputation.
    imputer = fits['ridge_combined'].named_steps['prepare'].named_transformers_['numeric']['impute']
    assert imputer.statistics_[(demo.NUMERIC + demo.INDICATORS).index('party_share_centre')] == 0
    for table in [objects, dates]:
        assert table.loc[table.model.eq('ridge_history_count'), 'delta_vs_history_count_pp'].eq(0).all()
    reference = scores.set_index('model').loc['ridge_history_count', 'mae_pp']
    np.testing.assert_allclose(scores.delta_vs_history_count_pp, scores.mae_pp - reference)


def test_reserved_dates_are_rejected_before_scoring():
    train, validation = sample_frames()
    validation['vote_date'] = pd.Timestamp('2023-01-01')
    with pytest.raises(ValueError, match='validation dates only'):
        eda.fit_comparisons(train, validation)

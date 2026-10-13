from dataclasses import replace

import pandas as pd
import pytest

from scripts.evaluate_votes import EvaluationConfig, evaluate
from scripts.feature_blocks import FeatureBlock


def rows_for_windows():
    rows = []
    for vote, date, shares, available in [
        ('train-a', '2020-01-01', [0.2, 0.4], '2020-01-02'),
        ('train-b', '2021-01-01', [0.3, 0.5], '2021-01-02'),
        ('valid-a', '2022-01-01', [0.8, 0.6], '2022-01-02'),
        ('valid-b', '2023-01-01', [0.9, 0.7], '2023-01-02'),
        ('test', '2024-01-01', [0.1, 0.9], '2024-01-02'),
    ]:
        for municipality, share in zip(['a', 'b'], shares):
            rows.append(dict(municipality_id=municipality, vote_id=vote, voting_date=date,
                yes_count=share * 100, no_count=(1-share) * 100, geography_id='g1',
                source_version='fixture-v1', result_available_at=available,
                result_availability_evidence='fixture-result-release',
                forecast_at=str(pd.Timestamp(date, tz='UTC')-pd.Timedelta(days=10)),
                forecast_evidence='fixture-brochure', is_special_unit=False,
                is_subsidiary=False, is_provisional=False))
    return pd.DataFrame(rows)


def feature_block():
    records = pd.DataFrame([dict(municipality_id=municipality, reference_date='2019-12-31',
        published_at='2020-01-01', availability_status='verified', availability_evidence='fixture-source',
        source_version='features-v1', geography_id='g1', population=value)
        for municipality, value in [('a', 100), ('b', 200)]])
    return FeatureBlock('population', 'municipality', records, ('population',), (),
        {'population': 'fixture population'}, 'fixture://population', 'features-v1')


def config(**changes):
    base = EvaluationConfig(('2020-01-01','2021-01-01'),
        ('2022-01-01','2023-01-01'), ('2024-01-01',), history_policy='rolling')
    return replace(base, **changes)


def test_declared_expanding_windows_refit_only_at_boundaries_and_exclude_test_scores():
    rows = rows_for_windows()
    # This result is published after the first window's brochure, then eligible
    # for the second window's later forecast.
    rows.loc[rows.vote_id.eq('train-b'), 'result_available_at'] = '2022-02-01'
    settings = config(validation_windows=(('2022-01-01',), ('2023-01-01',)),
        hist_gradient_boosting_candidates=((5, 1, .1, 10),))
    result = evaluate(rows, settings, feature_blocks=(feature_block(),))

    regularized = result['manifest']['regularized']['ridge_population']
    assert [window['training_dates'] for window in regularized['windows']] == [
        ['2020-01-01'],
        ['2020-01-01', '2021-01-01', '2022-01-01'],
    ]
    assert [window['validation_dates'] for window in regularized['windows']] == [
        ['2022-01-01'], ['2023-01-01']]
    assert all(window['fit_cutoff'] <= window['first_forecast_at'] for window in regularized['windows'])
    assert all('test' not in window['training_partitions'] for window in regularized['windows'])
    assert set(result['predictions'].query("model == 'ridge_population'").voting_date.dt.strftime('%Y-%m-%d')) == {
        '2022-01-01', '2023-01-01'}
    assert result['predictions'].raw_prediction.notna().all()
    assert result['predictions'].prediction.between(0, 1).all()
    assert 'clipping_fraction' in result['metrics']['ridge_population']

    boosted = result['manifest']['hist_gradient_boosting']['hist_gradient_boosting_population']
    assert [window['training_dates'] for window in boosted['windows']] == [
        ['2020-01-01'], ['2020-01-01', '2021-01-01', '2022-01-01']]
    assert [window['validation_dates'] for window in boosted['windows']] == [
        ['2022-01-01'], ['2023-01-01']]
    assert [window['fit_cutoff'] for window in boosted['windows']] == [
        '2020-01-02 00:00:00+00:00', '2022-02-01 00:00:00+00:00']
    assert all('fixed for every row in this window' in window['refit_schedule']
        for window in regularized['windows'] + boosted['windows'])


def test_available_nontext_blocks_have_a_common_comparison_model_and_keep_individual_blocks():
    second = feature_block()
    second = FeatureBlock('second', second.scope, second.records.assign(population=second.records.population * 2),
        second.numeric_features, second.categorical_features, second.definitions,
        second.source_url, second.source_version)
    rows, settings = rows_for_windows(), config()
    result = evaluate(rows, settings, feature_blocks=(feature_block(), second))

    models = set(result['predictions'].model)
    assert {'ridge_population', 'ridge_second', 'ridge_combined'} <= models
    prediction_keys = result['predictions'].groupby('model').apply(
        lambda group: set(zip(group.municipality_id, group.vote_id)), include_groups=False)
    assert prediction_keys['ridge_population'] == prediction_keys['ridge_second'] == prediction_keys['ridge_combined']
    assert set(result['ablations']) == {'population', 'second'}


@pytest.mark.parametrize('windows', [
    (('2022-01-01',),),
    (('2022-01-01','2023-01-01'), ('2023-01-01',)),
    (('2023-01-01',), ('2022-01-01',)),
])
def test_validation_windows_must_cover_validation_dates_once_in_chronological_order(windows):
    with pytest.raises(ValueError, match='validation window'):
        evaluate(rows_for_windows(), config(validation_windows=windows), feature_blocks=(feature_block(),))

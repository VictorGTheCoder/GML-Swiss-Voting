from dataclasses import replace

import pandas as pd
import pytest

from scripts.modeling.evaluate_votes import EvaluationConfig, evaluate
from scripts.modeling.feature_blocks import FeatureBlock


def prepared_rows():
    rows = []
    for vote, date, shares, available in [
        ('train-a', '2020-01-01', [.2, .4], '2020-01-02'),
        ('train-b', '2021-01-01', [.3, .5], '2021-01-02'),
        ('valid-a', '2022-01-01', [.8, .6], '2022-01-02'),
        ('valid-b', '2023-01-01', [.9, .7], '2023-01-02'),
        ('test', '2024-01-01', [.1, .9], '2024-01-02'),
    ]:
        for municipality, share in zip(['a', 'b'], shares):
            rows.append({'municipality_id': municipality, 'vote_id': vote, 'voting_date': date,
                'yes_count': share * 100, 'no_count': (1-share) * 100, 'geography_id': 'g1',
                'source_version': 'fixture-v1', 'result_available_at': available,
                'result_availability_evidence': 'fixture-result-release',
                'forecast_at': str(pd.Timestamp(date, tz='UTC')-pd.Timedelta(days=10)),
                'forecast_evidence': 'fixture-brochure', 'is_special_unit': False,
                'is_subsidiary': False, 'is_provisional': False})
    return pd.DataFrame(rows)


def population_block():
    records = pd.DataFrame([{'municipality_id': municipality, 'reference_date': '2019-12-31',
        'published_at': '2020-01-01', 'availability_status': 'verified', 'availability_evidence': 'fixture-source',
        'source_version': 'features-v1', 'geography_id': 'g1', 'population': value, 'language': language}
        for municipality, value, language in [('a', 100, 'fr'), ('b', 200, 'de')]])
    return FeatureBlock('population', 'municipality', records, ('population',), ('language',),
        {'population': 'fixture population', 'language': 'fixture language'},
        'fixture://population', 'features-v1')


def config(**changes):
    base = EvaluationConfig(('2020-01-01', '2021-01-01'),
        ('2022-01-01', '2023-01-01'), ('2024-01-01',), history_policy='rolling',
        ridge_alphas=(1.,), hist_gradient_boosting_candidates=((7, 2, .1, 10),))
    return replace(base, **changes)


def test_histogram_boosting_is_paired_reproducible_and_records_training_only_preparation():
    rows, settings, block = prepared_rows(), config(), population_block()
    result = evaluate(rows, settings, feature_blocks=(block,))
    model = 'hist_gradient_boosting_population'

    assert model in set(result['predictions'].model)
    predictions = result['predictions'].query('model == @model')
    ridge = result['predictions'].query("model == 'ridge_population'")
    assert set(zip(predictions.municipality_id, predictions.vote_id)) == set(zip(ridge.municipality_id, ridge.vote_id))
    assert predictions.prediction.between(0, 1).all()
    assert predictions.raw_prediction.notna().all()
    manifest = result['manifest']['hist_gradient_boosting'][model]
    assert manifest['settings'] == {'max_leaf_nodes': 7, 'min_samples_leaf': 2, 'learning_rate': .1, 'max_iter': 10}
    assert manifest['preprocessing'].startswith('training-only')
    assert all(window['fit_cutoff'] <= window['first_forecast_at'] for window in manifest['windows'])
    assert result['predictions'].equals(evaluate(rows, settings, feature_blocks=(block,))['predictions'])


def test_histogram_boosting_does_not_use_reserved_test_or_same_window_targets():
    rows, settings, block = prepared_rows(), config(), population_block()
    first = evaluate(rows, settings, feature_blocks=(block,))
    rows.loc[rows.vote_id.isin(['valid-a', 'valid-b', 'test']), 'yes_count'] = 1
    rows.loc[rows.vote_id.isin(['valid-a', 'valid-b', 'test']), 'no_count'] = 99
    second = evaluate(rows, settings, feature_blocks=(block,))
    model = 'hist_gradient_boosting_population'
    left = first['predictions'].query("model == @model and vote_id == 'valid-a'").prediction.tolist()
    right = second['predictions'].query("model == @model and vote_id == 'valid-a'").prediction.tolist()
    assert right == pytest.approx(left)
    report = second['manifest']['hist_gradient_boosting'][model]
    assert all('test' not in window.get('training_partitions', []) for window in report['windows'])
    assert set(second['predictions'].voting_date.dt.strftime('%Y-%m-%d')) == {'2022-01-01', '2023-01-01'}


def test_unseen_heldout_category_does_not_change_training_transform_or_other_predictions():
    rows, settings, block = prepared_rows(), config(validation_windows=(('2022-01-01',), ('2023-01-01',))), population_block()
    first = evaluate(rows, settings, feature_blocks=(block,))
    later_release = block.records.iloc[[0]].copy()
    later_release['reference_date'] = '2021-12-31'
    later_release['published_at'] = '2022-01-01'
    later_release['population'] = 999
    later_release['language'] = 'it'
    updated_block = FeatureBlock(block.block_id, block.scope,
        pd.concat([block.records, later_release], ignore_index=True), block.numeric_features,
        block.categorical_features, block.definitions, block.source_url, block.source_version)
    second = evaluate(rows, settings, feature_blocks=(updated_block,))
    model = 'hist_gradient_boosting_population'
    first_manifest = first['manifest']['hist_gradient_boosting'][model]
    second_manifest = second['manifest']['hist_gradient_boosting'][model]
    assert first_manifest['windows'][1]['training_design_sha256'] == second_manifest['windows'][1]['training_design_sha256']
    first_prediction = first['predictions'].query("model == @model and vote_id == 'valid-b' and municipality_id == 'b'").prediction.iloc[0]
    second_prediction = second['predictions'].query("model == @model and vote_id == 'valid-b' and municipality_id == 'b'").prediction.iloc[0]
    assert second_prediction == pytest.approx(first_prediction)


def test_invalid_histogram_boosting_configuration_fails_at_evaluation_seam():
    with pytest.raises(ValueError, match='hist_gradient_boosting_candidates'):
        evaluate(prepared_rows(), config(hist_gradient_boosting_candidates=()), feature_blocks=(population_block(),))
    with pytest.raises(ValueError, match='only be loaded in final_test'):
        evaluate(prepared_rows(), config(selected_hist_gradient_boosting={}), feature_blocks=(population_block(),))


def test_frozen_choices_cover_boosting_windows_and_explicit_text_policy():
    from scripts.modeling.final_evaluation import freeze_experiment

    rows = prepared_rows()
    settings = config(validation_windows=(('2022-01-01',), ('2023-01-01',)))
    validation = evaluate(rows, settings, feature_blocks=(population_block(),), text_records=[])
    frozen = freeze_experiment(validation)

    model = 'hist_gradient_boosting_population'
    assert frozen['selected_hist_gradient_boosting'][model] == {
        'max_leaf_nodes': 7, 'min_samples_leaf': 2, 'learning_rate': .1, 'max_iter': 10,
    }
    assert frozen['selection_judgment'].startswith('Prefer Ridge unless')
    assert frozen['signature']['validation_windows'] == [['2022-01-01'], ['2023-01-01']]
    assert frozen['signature']['text_policy'] == {
        'summary_field': 'summary_official', 'language': 'fr',
        'ngram_range': [1, 2], 'norm': 'l2', 'min_df': 2, 'max_df': .95,
        'max_features': 2000,
    }

    final_settings = replace(settings, mode='final_test', choices_frozen=True,
        selected_ridge_alphas=frozen['selected_ridge_alphas'],
        selected_hist_gradient_boosting=frozen['selected_hist_gradient_boosting'])
    final = evaluate(rows, final_settings, feature_blocks=(population_block(),),
        text_records=[], frozen_experiment=frozen)
    assert model in set(final['predictions'].model)
    assert any({pair['left_model'], pair['right_model']} == {model, 'ridge_population'}
        for pair in final['paired_uncertainty'])
    assert final['coverage'][model]['rows'] == 2
    assert {'clipped_rows', 'clipping_fraction', 'raw_prediction_min', 'raw_prediction_max'} <= set(final['metrics'][model])
    assert model in set(final['by_date'].model) and model in set(final['by_object'].model)

    changed_settings = replace(final_settings, selected_hist_gradient_boosting={
        **frozen['selected_hist_gradient_boosting'],
        model: {'max_leaf_nodes': 15, 'min_samples_leaf': 2, 'learning_rate': .1, 'max_iter': 10},
    })
    with pytest.raises(ValueError, match='frozen'):
        evaluate(rows, changed_settings, feature_blocks=(population_block(),),
            text_records=[], frozen_experiment=frozen)

    changed_schedule = replace(final_settings, validation_windows=(('2022-01-01', '2023-01-01'),))
    with pytest.raises(ValueError, match='frozen'):
        evaluate(rows, changed_schedule, feature_blocks=(population_block(),),
            text_records=[], frozen_experiment=frozen)


def test_final_boosting_fit_and_first_test_prediction_ignore_reserved_test_targets():
    from scripts.modeling.final_evaluation import freeze_experiment

    rows, block = prepared_rows(), population_block()
    settings = config(refit_train_validation=True)
    frozen = freeze_experiment(evaluate(rows, settings, feature_blocks=(block,)))
    final_settings = replace(settings, mode='final_test', choices_frozen=True,
        selected_ridge_alphas=frozen['selected_ridge_alphas'],
        selected_hist_gradient_boosting=frozen['selected_hist_gradient_boosting'])
    first = evaluate(rows, final_settings, feature_blocks=(block,), frozen_experiment=frozen)

    changed = rows.copy()
    changed.loc[changed.vote_id.eq('test'), 'yes_count'] = 99
    changed.loc[changed.vote_id.eq('test'), 'no_count'] = 1
    changed_validation = freeze_experiment(evaluate(changed, settings, feature_blocks=(block,)))
    assert changed_validation['selected_hist_gradient_boosting'] == frozen['selected_hist_gradient_boosting']
    assert changed_validation['selected_ridge_alphas'] == frozen['selected_ridge_alphas']
    second = evaluate(changed, final_settings, feature_blocks=(block,), frozen_experiment=frozen)
    model = 'hist_gradient_boosting_population'
    first_predictions = first['predictions'].query('model == @model').prediction.tolist()
    second_predictions = second['predictions'].query('model == @model').prediction.tolist()
    assert second_predictions == pytest.approx(first_predictions)
    fit = first['manifest']['hist_gradient_boosting'][model]
    assert all('test' not in window.get('training_partitions', []) for window in fit['windows'])

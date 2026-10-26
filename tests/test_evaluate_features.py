import pandas as pd
import pytest

from scripts.modeling.evaluate_votes import EvaluationConfig, evaluate, synthetic_example
from scripts.modeling.feature_blocks import FeatureBlock


def block(records=None, **changes):
    if records is None:
        records = pd.DataFrame([dict(municipality_id=key, reference_date='2018-12-31',
            published_at='2019-01-01', availability_status='verified', availability_evidence='release-archive',
            source_version='statpop-fixture-v1', geography_id='synthetic-g1', population=value,
            foreign_share=.2, language='fr') for key, value in [('a',100),('b',200),('c',300)]])
    return FeatureBlock(block_id='statpop', scope='municipality', records=records,
        numeric_features=('population','foreign_share'), categorical_features=('language',),
        definitions={'population':'resident population, persons', 'foreign_share':'foreign/population, share',
                     'language':'fixture categorical classification'},
        source_url='https://example.test/statpop', source_version='statpop-fixture-v1',
        geography_mode='historically_existing', **changes)


def test_pipeline_joins_prepared_features_and_reports_incremental_reference_on_same_keys():
    rows, config = synthetic_example()
    result = evaluate(rows, config, feature_blocks=(block(),))
    joined = result['joined_features'].set_index(['municipality_id','vote_id'])
    assert joined.loc[('a','next'),'statpop__population'] == 100
    assert result['coverage']['feature_blocks']['statpop']['matched_rows'] == 5
    assert set(result['metrics']) == {'constant','municipal_history','ridge_history','ridge_statpop',
        'hist_gradient_boosting_history','hist_gradient_boosting_statpop'}
    keys = result['predictions'].groupby('model').apply(lambda g: set(zip(g.municipality_id,g.vote_id)),include_groups=False)
    assert all(value == {('a','next'),('c','next')} for value in keys)
    assert result['manifest']['regularized']['ridge_statpop']['selected_alpha'] in config.ridge_alphas
    assert set(result['manifest']['regularized']['ridge_statpop']['training_dates']) == {'2020-01-01'}


def test_release_between_brochure_and_vote_unknown_time_and_geography_are_missing():
    rows, config = synthetic_example()
    records = block().records.copy()
    records.loc[records.municipality_id.eq('a'),'published_at'] = '2020-12-25'  # forecast December 22
    records.loc[records.municipality_id.eq('b'),'availability_evidence'] = None
    records.loc[records.municipality_id.eq('c'),'geography_id'] = 'incompatible'
    result = evaluate(rows, config, feature_blocks=(block(records),))
    report = result['join_report'].set_index(['municipality_id','vote_id'])
    assert report.loc[('a','next'),'status'] == 'unavailable_at_forecast'
    assert report.loc[('b','old'),'status'] == 'unknown_availability'
    assert report.loc[('c','next'),'status'] == 'incompatible_geography'
    assert result['joined_features'].query("vote_id == 'next'").statpop__population.isna().all()
    assert result['coverage']['feature_blocks']['statpop']['missing_values']['population'] == 4
    assert len(result['predictions'].query("model == 'ridge_statpop'")) == 2


def test_duplicate_release_keys_and_outcome_allowlists_fail_closed():
    rows, config = synthetic_example()
    records = block().records
    with pytest.raises(ValueError, match='duplicate'):
        evaluate(rows, config, feature_blocks=(block(pd.concat([records,records.iloc[[0]]])),))
    unsafe = FeatureBlock('unsafe','municipality',records.assign(yes_count=1),('yes_count',),(),
                          {'yes_count':'outcome'},'fixture','statpop-fixture-v1')
    with pytest.raises(ValueError, match='outcome'):
        evaluate(rows, config, feature_blocks=(unsafe,))


def test_frozen_reference_ignores_heldout_targets_and_training_transforms_ignore_heldout_features():
    rows, original = synthetic_example()
    config = EvaluationConfig(original.train_dates,original.validation_dates,original.test_dates,
                              choices_frozen=True,selected_ridge_alphas={'ridge_history':1.,'ridge_statpop':1.})
    records = block().records.copy()
    first = evaluate(rows,config,feature_blocks=(block(records),))
    rows.loc[rows.vote_id.eq('next'),'yes_count'] = 1
    rows.loc[rows.vote_id.eq('next'),'no_count'] = 99
    records.loc[records.municipality_id.eq('c'),'population'] = 10**9
    second = evaluate(rows,config,feature_blocks=(block(records),))
    assert second['manifest']['regularized']['ridge_statpop']['training_design_sha256'] == first['manifest']['regularized']['ridge_statpop']['training_design_sha256']
    # Municipality a's inputs did not change; validation labels cannot change its prediction.
    a_first = first['predictions'].query("municipality_id == 'a' and model == 'ridge_statpop'").prediction.iloc[0]
    a_second = second['predictions'].query("municipality_id == 'a' and model == 'ridge_statpop'").prediction.iloc[0]
    assert a_second == pytest.approx(a_first)
    history = first['joined_features'].set_index(['municipality_id','vote_id'])
    assert history.loc[('a','old'),'municipal_history'] == pytest.approx(.5)
    assert history.loc[('a','old'),'history_missing'] == 1
    assert history.loc[('a','next'),'municipal_history'] == pytest.approx(.2)


def test_final_regularized_run_never_selects_using_test_targets_and_late_labels_are_excluded():
    from scripts.modeling.final_evaluation import freeze_experiment
    rows, original = synthetic_example()
    rows.loc[rows.municipality_id.eq('b'),'result_available_at'] = '2023-01-01'
    features = (block(),)
    frozen = freeze_experiment(evaluate(rows, original, feature_blocks=features))
    config = EvaluationConfig(original.train_dates,original.validation_dates,original.test_dates,
        mode='final_test',choices_frozen=True,selected_ridge_alphas=frozen['selected_ridge_alphas'])
    first = evaluate(rows,config,feature_blocks=features,frozen_experiment=frozen)
    assert first['manifest']['regularized']['ridge_statpop']['training_rows'] == 1
    assert first['manifest']['regularized']['ridge_statpop']['validation_scores_pp'] == {}
    rows.loc[rows.vote_id.eq('final'),'yes_count'] = 1
    rows.loc[rows.vote_id.eq('final'),'no_count'] = 99
    assert evaluate(rows,config,feature_blocks=features,frozen_experiment=frozen)['predictions'].prediction.tolist() == first['predictions'].prediction.tolist()


def test_rolling_municipal_history_uses_training_only_global_fallback():
    rows, original = synthetic_example()
    later = rows.loc[rows.vote_id.eq('next')].iloc[[0]].copy()
    later['municipality_id'] = 'new-municipality'
    later['vote_id'] = 'later'
    later['voting_date'] = '2021-06-01'
    later['forecast_at'] = '2021-05-20'
    later['result_available_at'] = '2021-06-01'
    rows = pd.concat([rows,later],ignore_index=True)
    config = EvaluationConfig(original.train_dates,('2021-01-01','2021-06-01'),original.test_dates,history_policy='rolling')
    result = evaluate(rows,config,feature_blocks=(block(),))
    history = result['joined_features'].query("vote_id == 'later'")
    assert history.municipal_history.iloc[0] == pytest.approx(.4)
    assert result['manifest']['regularized']['ridge_statpop']['training_history_cold_start_share'] == .5


def test_statpop_prepared_adapter_requires_real_publication_evidence_and_computes_defined_share():
    from scripts.modeling.feature_blocks import prepare_statpop_nationality
    rows, config = synthetic_example()
    prepared = pd.DataFrame({'year':[2018,2018,2018],'code':['a','b','c'],
                             'population':[100,200,300],'swiss':[80,160,240],'foreign':[20,40,60]})
    source = dict(source_version='statpop-fixture-v1', geography_id='synthetic-g1',
                  source_url='https://example.test/statpop')
    unavailable = prepare_statpop_nationality(prepared,**source)
    result = evaluate(rows,config,feature_blocks=(unavailable,))
    assert result['coverage']['feature_blocks']['statpop_nationality']['unknown_availability_rows'] == 5
    evidence = pd.DataFrame({'year':[2018]*3,'code':['a','b','c'],'published_at':['2019-01-01']*3,
                            'availability_evidence':['archive']*3,'source_version':['statpop-fixture-v1']*3})
    available = prepare_statpop_nationality(prepared,publication_evidence=evidence,**source)
    result = evaluate(rows,config,feature_blocks=(available,))
    assert result['joined_features'].statpop_nationality__foreign_share.tolist() == pytest.approx([.2]*5)
    assert result['manifest']['feature_blocks']['statpop_nationality']['definitions']['population'] == 'Permanent resident population, persons'


def test_asof_join_selects_latest_verified_version_before_forecast():
    rows, config = synthetic_example()
    records = block().records
    update = records.loc[records.municipality_id.eq('a')].copy()
    update['reference_date'] = '2019-12-31'
    update['published_at'] = '2020-02-01'
    update['population'] = 150
    records = pd.concat([records,update],ignore_index=True)
    result = evaluate(rows,config,feature_blocks=(block(records),))
    features = result['joined_features'].set_index(['municipality_id','vote_id'])
    assert features.loc[('a','old'),'statpop__population'] == 100
    assert features.loc[('a','next'),'statpop__population'] == 150
    report = result['join_report'].set_index(['municipality_id','vote_id'])
    assert report.loc[('a','next'),'published_at'] == '2020-02-01 00:00:00+00:00'


def test_shared_history_respects_forecast_context_geography_and_training_fallback():
    from dataclasses import replace
    rows,config = synthetic_example()
    # Two objects on the same voting day have different forecast cutoffs.
    other = rows.loc[rows.vote_id.eq('next')].copy()
    other['vote_id'] = 'early-brochure'
    other['forecast_at'] = '2019-12-15'
    rows = pd.concat([rows,other],ignore_index=True)
    rows.loc[rows.municipality_id.eq('b'),'result_available_at'] = '2020-12-24'
    rows.loc[rows.vote_id.eq('early-brochure'),'geography_id'] = 'different-boundary'
    result = evaluate(rows,config,feature_blocks=(block(),))
    # At the early brochure neither historical result exists; both baselines abstain.
    assert set(result['predictions'].vote_id) == {'next'}
    values = result['joined_features'].set_index(['municipality_id','vote_id'])
    assert values.loc[('a','early-brochure'),'municipal_history'] == pytest.approx(.5)
    assert values.loc[('a','early-brochure'),'history_missing'] == 1
    # B's late publication cannot enter the next forecast's global fallback.
    assert values.loc[('c','next'),'municipal_history'] == pytest.approx(.2)
    assert result['predictions'].query("model == 'constant'").prediction.tolist() == pytest.approx([.2,.2])
    rows.loc[rows.vote_id.eq('next'),'geography_id'] = 'different-boundary'
    result = evaluate(rows,replace(config,history_policy='rolling'),feature_blocks=(block(),))
    values = result['joined_features'].query("vote_id == 'next'")
    assert values.history_missing.tolist() == [1.,1.]
    assert values.municipal_history.tolist() == pytest.approx([.2,.2])


def test_release_indexing_preserves_allowed_feature_named_verified():
    from dataclasses import replace
    rows,config = synthetic_example()
    source = block()
    source = replace(source,records=source.records.assign(verified=42),
                     numeric_features=source.numeric_features+('verified',),
                     definitions=source.definitions|{'verified':'fixture numerical feature'})
    result = evaluate(rows,config,feature_blocks=(source,))
    assert result['joined_features'].statpop__verified.tolist() == [42]*5


@pytest.mark.parametrize('name', [
    'evaluation_weight', 'evaluation_weights', 'eval_weight', 'electorate_weight',
    'sample_weight', 'scoring_weight', 'metric_weight', 'row_weight',
    'evaluation_weight_latest',
])
def test_evaluation_only_weights_cannot_be_feature_block_predictors(name):
    from dataclasses import replace

    rows, config = synthetic_example()
    source = block()
    unsafe = replace(source, records=source.records.assign(**{name: 42}),
                     numeric_features=source.numeric_features + (name,),
                     definitions=source.definitions | {name: 'Retrospective evaluation weight'})
    with pytest.raises(ValueError, match='evaluation-only'):
        evaluate(rows, config, feature_blocks=(unsafe,))


def test_history_identifier_is_reserved_and_unmatched_blocks_are_not_fitted():
    from dataclasses import replace

    rows, config = synthetic_example()
    with pytest.raises(ValueError, match='reserved'):
        evaluate(rows, config, feature_blocks=(replace(block(), block_id='history'),))

    source = block()
    unmatched = replace(source, records=source.records.assign(availability_status='unknown'))
    result = evaluate(rows, config, feature_blocks=(unmatched,))
    assert result['coverage']['feature_blocks']['statpop']['matched_rows'] == 0
    assert 'ridge_statpop' not in result['metrics']
    assert result['ablations']['statpop']['status'] == 'skipped'
    assert result['ablations']['statpop']['prerequisite_reason'] == 'No admissible source matches at forecast time'

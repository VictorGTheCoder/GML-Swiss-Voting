from dataclasses import replace

import pandas as pd
import pytest

from scripts.evaluate_votes import evaluate, synthetic_example
from scripts.feature_blocks import synthetic_feature_example


def test_complete_date_paired_uncertainty_is_deterministic_and_reports_grouped_sampling():
    rows, config = synthetic_example()
    later = rows.loc[rows.vote_id.eq('next')].iloc[[0]].copy()
    later['vote_id'] = 'later'
    later['voting_date'] = '2021-06-01'
    later['forecast_at'] = '2021-05-20'
    later['result_available_at'] = '2021-06-01'
    later['yes_count'],later['no_count'] = 50,50
    rows = pd.concat([rows,later],ignore_index=True)
    config = replace(config,validation_dates=('2021-01-01','2021-06-01'),bootstrap_replicates=40,seed=7)
    first = evaluate(rows,config)
    second = evaluate(rows,config)
    assert first['paired_uncertainty'] == second['paired_uncertainty']
    pair = first['paired_uncertainty'][0]
    assert pair['paired_rows'] == 3
    assert pair['paired_dates'] == 2
    assert pair['difference_mae_pp'] == pytest.approx(40/3)
    for sample in pair['sampling_audit']:
        assert sample['sampled_rows'] == sum({'2021-01-01':2,'2021-06-01':1}[date] for date in sample['dates'])
    assert 'serial dependence' in pair['limitations']


def test_validation_freeze_controls_final_features_sources_and_refit():
    from scripts.final_evaluation import freeze_experiment
    rows, config = synthetic_example()
    blocks = (synthetic_feature_example(),)
    validation = evaluate(rows,config,feature_blocks=blocks,text_records=[])
    frozen = freeze_experiment(validation)
    final_config = replace(config,mode='final_test',choices_frozen=True,selected_ridge_alphas=frozen['selected_ridge_alphas'])
    final = evaluate(rows,final_config,feature_blocks=blocks,text_records=[],frozen_experiment=frozen)
    assert set(final['predictions'].vote_id) == {'final'}
    assert final['text_experiment']['status'] == 'skipped'
    assert final['manifest']['frozen_experiment_sha256'] == frozen['sha256']
    with pytest.raises(ValueError,match='frozen'):
        evaluate(rows,replace(final_config,history_policy='rolling'),feature_blocks=blocks,text_records=[],frozen_experiment=frozen)
    with pytest.raises(ValueError,match='validation'):
        freeze_experiment(final)


def test_declared_final_refit_adds_validation_labels_and_rolling_test_history_uses_only_published_past():
    from scripts.final_evaluation import freeze_experiment
    rows, config = synthetic_example()
    later = rows.loc[rows.vote_id.eq('final')].copy()
    later['vote_id'] = 'test-later'
    later['voting_date'] = '2022-06-01'
    later['forecast_at'] = '2022-05-20'
    later['result_available_at'] = '2022-06-01'
    rows = pd.concat([rows,later],ignore_index=True)
    config = replace(config,test_dates=('2022-01-01','2022-06-01'),refit_train_validation=True,history_policy='rolling')
    blocks = (synthetic_feature_example(),)
    frozen = freeze_experiment(evaluate(rows,config,feature_blocks=blocks))
    final_config = replace(config,mode='final_test',choices_frozen=True,selected_ridge_alphas=frozen['selected_ridge_alphas'])
    final = evaluate(rows,final_config,feature_blocks=blocks,frozen_experiment=frozen)
    assert final['manifest']['regularized']['ridge_history']['training_rows'] == 4
    assert set(final['manifest']['regularized']['ridge_history']['training_dates']) == {'2020-01-01','2021-01-01'}
    last = final['predictions'].query("vote_id == 'test-later' and model == 'municipal_history'")
    assert last.prediction.iloc[0] == pytest.approx((.2+.8+.9)/3)
    history = final['joined_features'].query("vote_id == 'test-later'")
    assert history.municipal_history.iloc[0] == pytest.approx((.2+.8+.9)/3)
    rows.loc[rows.vote_id.eq('final'),'result_available_at'] = '2022-07-01'
    with pytest.raises(ValueError,match='frozen'):
        evaluate(rows,final_config,feature_blocks=blocks,frozen_experiment=frozen)
    revised_frozen = freeze_experiment(evaluate(rows,config,feature_blocks=blocks))
    revised_config = replace(final_config,selected_ridge_alphas=revised_frozen['selected_ridge_alphas'])
    final = evaluate(rows,revised_config,feature_blocks=blocks,frozen_experiment=revised_frozen)
    assert final['predictions'].query("vote_id == 'test-later' and model == 'municipal_history'").prediction.iloc[0] == pytest.approx(.5)


def test_weighted_pair_reports_keep_evaluation_weights_out_of_predictors():
    rows,config = synthetic_example()
    rows['evaluation_weight'] = [1,1,1,3,2]
    config = replace(config,evaluation_weight_origin='synthetic retrospective electorate counts')
    result = evaluate(rows,config)
    assert result['manifest']['weight_origin'] == 'synthetic retrospective electorate counts'
    pair = result['paired_uncertainty'][0]
    assert pair['weighted_difference_mae_pp'] == pytest.approx(5)


def test_text_final_refit_uses_unique_declared_objects_and_keeps_weighted_errors():
    from scripts.final_evaluation import freeze_experiment
    from scripts.text_votes import synthetic_text_example
    rows,config = synthetic_example()
    rows['evaluation_weight'] = [1,1,1,3,2]
    config = replace(config,refit_train_validation=True,evaluation_weight_origin='synthetic electorate fixture')
    records = synthetic_text_example(rows)
    records[-1]['text'] = 'forbiddenfinaltoken'
    blocks = (synthetic_feature_example(),)
    frozen = freeze_experiment(evaluate(rows,config,feature_blocks=blocks,text_records=records))
    final_config = replace(config,mode='final_test',choices_frozen=True,selected_ridge_alphas=frozen['selected_ridge_alphas'])
    final = evaluate(rows,final_config,feature_blocks=blocks,text_records=records,frozen_experiment=frozen)
    text = final['text_experiment']
    assert text['representation']['training_objects'] == ['next','old']
    assert 'forbiddenfinaltoken' not in text['representation']['vocabulary']
    assert text['models']['paired_text']['training']['rows'] == 4
    assert text['metrics']['paired_text']['weighted_rows'] == 1
    assert text['metrics']['paired_text']['weight_origin'] == 'synthetic electorate fixture'
    assert text['by_object'][0]['electorate_weighted_mae_pp'] is not None
    assert any(pair['left_model'] == 'paired_nontext' and pair['right_model'] == 'paired_text' for pair in final['paired_uncertainty'])


def test_validation_skipped_text_stays_skipped_after_declared_refit_without_losing_nontext():
    from scripts.final_evaluation import freeze_experiment
    from scripts.text_votes import synthetic_text_example
    rows,config = synthetic_example()
    config = replace(config,refit_train_validation=True)
    records = synthetic_text_example(rows)
    records[0]['semantic_status'] = 'INVESTIGATE'
    blocks = (synthetic_feature_example(),)
    validation = evaluate(rows,config,feature_blocks=blocks,text_records=records)
    assert validation['text_experiment']['status'] == 'skipped'
    frozen = freeze_experiment(validation)
    final_config = replace(config,mode='final_test',choices_frozen=True,selected_ridge_alphas=frozen['selected_ridge_alphas'])
    final = evaluate(rows,final_config,feature_blocks=blocks,text_records=records,frozen_experiment=frozen)
    assert final['text_experiment']['status'] == 'skipped'
    assert final['metrics']['ridge_history']['rows'] == 1
    assert final['paired_uncertainty'][0]['interval_status'] == 'insufficient_dates'

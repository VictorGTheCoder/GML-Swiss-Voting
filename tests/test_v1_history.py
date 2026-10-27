import pandas as pd
from scripts.evaluate_votes import EvaluationConfig
from scripts.voting_history import build_v1_history_features

def test_equal_objects_context_and_unknown_evidence():
    source = pd.DataFrame([dict(municipality_id="a", geography_id="g", vote_id=v, voting_date=d, yes_count=y, no_count=n, result_available_at=d, result_availability_evidence="proof", source_version="v1", partition="context") for v,d,y,n in [("old","2010-02-01",1,9),("recent","2015-01-01",90,10),("same","2015-02-01",0,100)]])
    target = pd.DataFrame([dict(municipality_id="a",geography_id="g",vote_id="target",voting_date="2015-02-01",forecast_at="2015-01-20",partition="train")])
    config=EvaluationConfig(("2015-02-01",),("2016-01-01",),("2017-01-01",))
    result=build_v1_history_features(target,source,config)
    assert result.loc[0,"history_yes_mean"] == .5
    assert result.loc[0,"history_vote_count"] == 2
    assert result.loc[0,"history_5y_vote_count"] == 2
    assert result.loc[0,"history_same_domain_status"] == "unknown_domain_metadata"
    source.loc[0,"result_availability_evidence"]=None
    result=build_v1_history_features(target,source,config)
    assert result.loc[0,"history_status"] == "unknown_result_publication"
    assert pd.isna(result.loc[0,"history_vote_count"])


def test_evaluator_recomputes_frozen_rolling_and_keeps_context_out_of_fitting():
    from dataclasses import replace
    from scripts.evaluate_votes import evaluate, synthetic_example
    rows, config = synthetic_example()
    old=rows.iloc[[0]].copy()
    old['vote_id']='context'
    old['voting_date']='2010-01-01'
    old['forecast_at']='2009-12-01'
    old['result_available_at']='2010-01-01'
    old['yes_count']=100
    old['no_count']=0
    source=pd.concat([old,rows],ignore_index=True)
    frozen=evaluate(rows,config,history_source=source)
    finalconfig=replace(config,history_policy='rolling')
    rolling=evaluate(rows,finalconfig,history_source=source)
    # Training-only diagnostic history contains context without fitting it.
    assert len(frozen['eligible_rows'])==5
    a=frozen['history_report'].query("municipality_id == 'a' and vote_id == 'final'").iloc[0]
    b=rolling['history_report'].query("municipality_id == 'a' and vote_id == 'final'").iloc[0]
    assert a.history_yes_mean == .6
    assert b.history_yes_mean == 2/3
    changed=source.copy()
    changed.loc[changed.vote_id.eq('next'),'yes_count']=0
    changed.loc[changed.vote_id.eq('next'),'no_count']=100
    again=evaluate(rows,config,history_source=changed)
    pd.testing.assert_frame_equal(frozen['history_report'],again['history_report'])

def test_calendar_boundary_domain_dedup_and_publication_cutoff():
    source=pd.DataFrame([dict(municipality_id='a',geography_id='g',vote_id=v,voting_date=d,yes_count=y,no_count=100-y,result_available_at=pub,result_availability_evidence='proof',source_version='v') for v,d,y,pub in [('outside','2010-02-27',10,'2010-02-27'),('boundary','2010-02-28',20,'2010-02-28'),('late','2014-01-01',80,'2015-03-01'),('same','2015-04-01',100,'2015-01-01')]])
    target=pd.DataFrame([dict(municipality_id='a',geography_id='g',vote_id='target',voting_date='2015-04-01',forecast_at='2015-02-28',partition='train')])
    config=EvaluationConfig(('2015-04-01',),('2016-01-01',),('2017-01-01',))
    domains=pd.DataFrame([dict(vote_id=v,domain_codes=(1,2),domain_status='known',object_match_status='validated',object_match_evidence='exact',availability_status='verified',availability_evidence='proof',published_at='2010-01-01',reference_date='2010-01-01',source_version='v') for v in ['outside','boundary','late','same','target']])
    result=build_v1_history_features(target,source,config,domains).iloc[0]
    assert result.history_5y_yes_mean == .2
    assert result.history_5y_vote_count == 1
    assert result.history_same_domain_vote_count == 2
    assert abs(result.history_same_domain_yes_mean-.15)<1e-12
    source.loc[source.vote_id.eq('late'),'result_available_at']='2015-02-28'
    after=build_v1_history_features(target,source,config,domains).iloc[0]
    assert after.history_5y_yes_mean == .5
    assert after.history_same_domain_vote_count == 3
    target['municipality_id']='missing'
    empty=build_v1_history_features(target,source,config,domains).iloc[0]
    assert empty.history_vote_count == 0
    assert empty.history_missing
    assert empty.history_status == 'no_antecedents'


def test_complete_preparation_preserves_unknown_history_as_unresolved():
    from test_modeling_v1 import fixture_sources
    from scripts.integration.modeling_v1 import prepare_v1_table
    outcomes, objects, municipal=fixture_sources()
    config=EvaluationConfig(('2018-03-04',),('2019-01-01',),('2020-01-01',))
    result=prepare_v1_table(outcomes,geography_id='fixture-g1',source_version='fixture-v',municipal_blocks=municipal,object_features=objects,history_config=config)
    row=result.prepared.iloc[0]
    assert row.history_status == 'unknown_target_dates'
    assert pd.isna(row.history_vote_count)
    assert pd.isna(row.history_missing)
    assert result.strict_population.empty


def test_evaluator_rejects_unproved_or_invalid_history_publication_and_ignores_claimed_partition():
    from scripts.evaluate_votes import evaluate, synthetic_example
    rows, config = synthetic_example()
    source = rows.copy()
    # A caller cannot relabel held-out results as training history.
    source['partition'] = 'train'
    original = evaluate(rows, config, history_source=source)
    final = original['history_report'].query("vote_id == 'final'").iloc[0]
    assert final.history_vote_count == 1
    for field, value, status in (
        ('result_available_at', '2019-01-01', 'invalid_result_publication'),
        ('result_availability_evidence', None, 'unknown_result_publication'),
        ('result_availability_status', 'unknown', 'unknown_result_publication'),
        ('result_source_version', None, 'unknown_result_publication'),
    ):
        changed = source.copy()
        if field in ('result_availability_status','result_source_version'):
            changed[field] = 'verified' if field == 'result_availability_status' else 'fixture-version'
        changed.loc[changed.vote_id.eq('old'), field] = value
        result = evaluate(rows, config, history_source=changed)
        final = result['history_report'].query("vote_id == 'final'").iloc[0]
        assert final.history_status == status
        assert pd.isna(final.history_vote_count)
        assert 'ridge_v1_history' not in set(result['predictions'].model)


def test_frozen_v1_context_signature_reserves_final_labels_and_ignores_outcome_extras():
    from dataclasses import replace
    from scripts.evaluate_votes import evaluate, synthetic_example
    from scripts.final_evaluation import freeze_experiment
    rows, config = synthetic_example()
    source = rows.copy()
    source['yes_share'] = source.yes_count / (source.yes_count + source.no_count)
    frozen = freeze_experiment(evaluate(rows, config, history_source=source))
    final_config = replace(config, mode='final_test', choices_frozen=True,
                           selected_ridge_alphas=frozen['selected_ridge_alphas'])
    changed = source.copy()
    changed.loc[changed.vote_id.eq('final'), 'yes_count'] = 0
    changed.loc[changed.vote_id.eq('final'), 'yes_share'] = 0
    result = evaluate(rows, final_config, history_source=changed, frozen_experiment=frozen)
    assert result['manifest']['frozen_experiment_sha256'] == frozen['sha256']


def test_evaluator_skips_unknown_history_family_but_keeps_baseline_predictions():
    from scripts.evaluate_votes import evaluate, synthetic_example
    rows, config = synthetic_example()
    result = evaluate(rows, config, history_source=rows)
    assert 'ridge_v1_history' not in set(result['predictions'].model)
    assert {'constant','municipal_history'} <= set(result['predictions'].model)
    report = result['manifest']['computed_history']
    assert report['status'] == 'skipped'
    assert report['reason'] == 'unresolved_history_availability'
    assert report['unresolved_status_counts']['history_same_domain']['unknown_domain_metadata'] > 0


def test_evaluator_allows_known_no_antecedent_means_to_use_training_imputation():
    from scripts.evaluate_votes import evaluate, synthetic_example
    rows, config = synthetic_example()
    domains = pd.DataFrame([dict(
        vote_id=vote, domain_codes=(1,), domain_status='known', object_match_status='validated',
        object_match_evidence='fixture exact match', availability_status='verified',
        availability_evidence='fixture publication', published_at='2000-01-01',
        reference_date='2000-01-01', source_version='fixture-domain-v1',
    ) for vote in rows.vote_id.unique()])
    result = evaluate(rows, config, history_source=rows, domain_records=domains)
    assert 'ridge_v1_history' in set(result['predictions'].model)
    assert result['manifest']['computed_history']['status'] == 'enabled'
    train = result['history_report'].query("vote_id == 'old'")
    assert train.history_same_domain_status.eq('no_antecedents').all()
    assert train.history_same_domain_yes_mean.isna().all()


def test_frozen_final_preserves_history_family_skipped_during_validation():
    from dataclasses import replace
    from scripts.evaluate_votes import evaluate, synthetic_example
    from scripts.final_evaluation import freeze_experiment
    rows, config = synthetic_example()
    domains = pd.DataFrame([dict(
        vote_id=vote, domain_codes=(1,), domain_status='known', object_match_status='validated',
        object_match_evidence='fixture exact match', availability_status='verified',
        availability_evidence='fixture publication',
        published_at='2021-02-01' if vote == 'next' else '2010-01-01',
        reference_date='2010-01-01', source_version='fixture-domain-v1',
    ) for vote in rows.vote_id.unique()])
    validation = evaluate(rows, config, history_source=rows, domain_records=domains)
    assert validation['manifest']['computed_history']['status'] == 'skipped'
    frozen = freeze_experiment(validation)
    final_config = replace(config, mode='final_test', choices_frozen=True,
                           selected_ridge_alphas=frozen['selected_ridge_alphas'])
    final = evaluate(rows, final_config, history_source=rows, domain_records=domains,
                     frozen_experiment=frozen)
    assert 'ridge_v1_history' not in set(final['predictions'].model)
    assert {'constant','municipal_history'} <= set(final['predictions'].model)
    assert final['manifest']['computed_history']['status'] == 'skipped'
    assert final['manifest']['computed_history']['reason'] == 'skipped_in_frozen_validation'


def test_frozen_final_reports_newly_unresolved_history_without_imputing_it():
    from dataclasses import replace
    from scripts.evaluate_votes import evaluate, synthetic_example
    from scripts.final_evaluation import freeze_experiment
    rows, config = synthetic_example()
    domains = pd.DataFrame([dict(
        vote_id=vote, domain_codes=(1,), domain_status='known', object_match_status='validated',
        object_match_evidence='fixture exact match', availability_status='verified',
        availability_evidence='fixture publication',
        published_at='2023-01-01' if vote == 'final' else '2010-01-01',
        reference_date='2010-01-01', source_version='fixture-domain-v1',
    ) for vote in rows.vote_id.unique()])
    validation = evaluate(rows, config, history_source=rows, domain_records=domains)
    assert validation['manifest']['computed_history']['status'] == 'enabled'
    frozen = freeze_experiment(validation)
    final_config = replace(config, mode='final_test', choices_frozen=True,
                           selected_ridge_alphas=frozen['selected_ridge_alphas'])
    final = evaluate(rows, final_config, history_source=rows, domain_records=domains,
                     frozen_experiment=frozen)
    assert 'ridge_v1_history' not in set(final['predictions'].model)
    assert final['manifest']['computed_history']['status'] == 'skipped'
    assert final['manifest']['computed_history']['reason'] == 'unresolved_history_availability'

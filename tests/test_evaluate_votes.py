import pandas as pd
import pytest

from scripts.evaluate_votes import EvaluationConfig, evaluate


def row(municipality, vote, date, yes, forecast=None, **changes):
    record = dict(municipality_id=municipality, vote_id=vote, voting_date=date,
                  yes_count=yes, no_count=100-yes, geography_id='g1', source_version='fixture-v1',
                  result_available_at=date, result_availability_evidence='fixture-publication',
                  forecast_at=forecast or str(pd.Timestamp(date) - pd.Timedelta(days=10)),
                  forecast_evidence='fixture-brochure', is_special_unit=False,
                  is_subsidiary=False, is_provisional=False)
    return record | changes


def prepared():
    return pd.DataFrame([row('a','old','2020-01-01',20), row('b','old','2020-01-01',60),
                         row('a','next','2021-01-01',80), row('c','next','2021-01-01',40),
                         row('a','final','2022-01-01',90)])


def config(**changes):
    return EvaluationConfig(train_dates=('2020-01-01',), validation_dates=('2021-01-01',),
                            test_dates=('2022-01-01',), **changes)


def test_pipeline_predicts_hand_checked_baselines_and_reserves_test():
    result = evaluate(prepared(), config())
    predictions = result['predictions'].set_index(['model','municipality_id'])
    assert predictions.loc[('constant','a'), 'prediction'] == pytest.approx(.4)
    assert predictions.loc[('municipal_history','a'), 'prediction'] == pytest.approx(.2)
    assert predictions.loc[('municipal_history','c'), 'prediction'] == pytest.approx(.4)
    assert result['metrics']['constant']['mae_pp'] == pytest.approx(20)
    assert result['metrics']['municipal_history']['mae_pp'] == pytest.approx(30)
    assert result['coverage']['municipal_history']['fallback_rows'] == 1
    assert set(result['predictions'].vote_id) == {'next'}
    assert result['manifest']['mode'] == 'validation'
    assert result['partitions'].groupby('voting_date').partition.nunique().max() == 1


def test_pipeline_excludes_invalid_and_ambiguous_rows_with_reason_counts():
    extra = [row('d','next','2021-01-01',20,is_special_unit=True),
             row('e','next','2021-01-01',20,is_subsidiary=True),
             row('f','next','2021-01-01',20,is_provisional=True),
             row('g','next','2021-01-01',0,no_count=0),
             row('h','unknown','2021-01-01',20,forecast_evidence=None),
             row('i','next','2021-01-01',20,geography_id=None),
             row('j','duplicate','2021-01-01',20), row('j','duplicate','2021-01-01',30)]
    result = evaluate(pd.concat([prepared(), pd.DataFrame(extra)], ignore_index=True), config())
    assert result['exclusions'] == {'special_unit': 1, 'subsidiary': 1, 'provisional': 1,
                                    'undefined_target': 1, 'forecast_evidence_missing': 1,
                                    'geography_missing': 1, 'duplicate_key': 2}
    assert set(result['predictions'].municipality_id) == {'a','c'}
    assert result['manifest']['input_rows'] == 13


def test_publication_cutoff_and_geography_apply_to_history_and_constant():
    data = prepared()
    # B's result appeared after prediction, despite an earlier statistical date.
    data.loc[data.municipality_id.eq('b'), 'result_available_at'] = '2021-01-01'
    data.loc[data.vote_id.eq('next'), 'geography_id'] = 'new-boundary'
    result = evaluate(data, config())
    assert result['predictions'].prediction.tolist() == pytest.approx([.2,.2,.2,.2])
    assert result['coverage']['municipal_history']['fallback_rows'] == 2
    data.loc[data.vote_id.eq('old'), 'result_availability_evidence'] = None
    result = evaluate(data, config())
    assert result['predictions'].empty
    assert result['coverage']['unpredictable_rows'] == 2
    assert result['exclusions']['no_admissible_training_history'] == 2


def test_rolling_history_updates_only_after_publication_and_frozen_targets_do_not_leak():
    data = pd.concat([prepared(), pd.DataFrame([row('a','later','2021-06-01',50)])], ignore_index=True)
    options = dict(train_dates=('2020-01-01',), validation_dates=('2021-01-01','2021-06-01'),
                   test_dates=('2022-01-01',))
    frozen = evaluate(data, EvaluationConfig(**options))
    rolling = evaluate(data, EvaluationConfig(**options, history_policy='rolling'))
    def prediction(result):
        return result['predictions'].query("vote_id == 'later' and model == 'municipal_history'").prediction.iloc[0]
    assert prediction(frozen) == pytest.approx(.2)
    assert prediction(rolling) == pytest.approx(.5)
    data.loc[data.vote_id.eq('next'), 'yes_count'] = 10
    data.loc[data.vote_id.eq('next'), 'no_count'] = 90
    assert prediction(evaluate(data, EvaluationConfig(**options))) == pytest.approx(.2)
    data.loc[data.vote_id.eq('next'), 'result_available_at'] = '2021-07-01'
    assert prediction(evaluate(data, EvaluationConfig(**options, history_policy='rolling'))) == pytest.approx(.2)


@pytest.mark.parametrize('changes, message', [
    ({'validation_dates': ('2020-01-01',)}, 'disjoint'),
    ({'train_dates': ('2021-01-01',), 'validation_dates': ('2020-01-01',)}, 'chronological'),
    ({'predictor_allowlist': ('yes_count',)}, 'allowlist'),
    ({'history_policy': 'silent'}, 'history_policy'),
    ({'mode': 'final_test'}, 'frozen'),
])
def test_invalid_experiment_configuration_fails_before_scoring(changes, message):
    options = dict(train_dates=('2020-01-01',), validation_dates=('2021-01-01',), test_dates=('2022-01-01',))
    with pytest.raises(ValueError, match=message):
        evaluate(prepared(), EvaluationConfig(**(options | changes)))


def test_final_test_requires_frozen_choices_and_audits_coverage_and_weights():
    data = prepared()
    data['evaluation_weight'] = [1, 1, 1, 3, 2]
    result = evaluate(data, config(mode='final_test', choices_frozen=True))
    assert set(result['predictions'].vote_id) == {'final'}
    assert result['metrics']['municipal_history']['mae_pp'] == pytest.approx(70)
    assert result['metrics']['municipal_history']['electorate_weighted_mae_pp'] == pytest.approx(70)
    assert result['coverage']['partitions']['validation'] == {'rows': 2, 'objects': 1, 'dates': 1}
    assert result['manifest']['predictor_allowlist'] == ('municipal_history','history_missing')
    assert result['manifest']['input_sha256'] == evaluate(data, config(mode='final_test', choices_frozen=True))['manifest']['input_sha256']
    assert not result['by_date'].empty


def test_multiple_objects_stay_on_one_date_and_extra_outcomes_are_not_predictors():
    extra = pd.DataFrame([row('a','other','2021-01-01',10)])
    data = pd.concat([prepared(), extra], ignore_index=True)
    result = evaluate(data, config())
    assert result['coverage']['partitions']['validation'] == {'rows': 3, 'objects': 2, 'dates': 1}
    data['same_object_turnout'] = 10**9
    data['electorate_count'] = 10**8
    changed = evaluate(data, config())
    assert changed['predictions'].prediction.tolist() == result['predictions'].prediction.tolist()


def test_audit_flags_and_missing_real_contract_are_explicit():
    data = prepared()
    data['flag_yes_no_gt_valid'] = [False, False, True, False, False]
    result = evaluate(data, config())
    assert result['exclusions']['audit_flag_yes_no_gt_valid'] == 1
    with pytest.raises(ValueError, match='forecast_evidence'):
        evaluate(data.drop(columns='forecast_evidence'), config())


def test_calendar_day_cannot_cross_partitions_even_when_timestamps_differ():
    options = dict(train_dates=('2020-01-01T00:00:00',),
                   validation_dates=('2020-01-01T12:00:00',),test_dates=('2022-01-01',))
    with pytest.raises(ValueError,match='disjoint'):
        evaluate(prepared(),EvaluationConfig(**options))
    data = prepared()
    data.loc[data.municipality_id.eq('b'),'voting_date'] = '2020-01-01T12:00:00Z'
    data.loc[data.vote_id.eq('next'),'voting_date'] = '2021-01-01T12:00:00Z'
    result = evaluate(data,config())
    assert result['coverage']['partitions']['train']['rows'] == 2
    assert result['coverage']['partitions']['validation']['rows'] == 2
    assert result['partitions'].groupby('voting_date').partition.nunique().max() == 1


def test_blank_source_versions_are_excluded_from_prepared_outcomes():
    from scripts.evaluate_votes import evaluate, synthetic_example

    rows, config = synthetic_example()
    rows.loc[(rows.vote_id == 'old') & (rows.municipality_id == 'a'), 'source_version'] = ''
    rows.loc[(rows.vote_id == 'next') & (rows.municipality_id == 'a'), 'source_version'] = '  '
    result = evaluate(rows, config)
    assert result['exclusions']['source_version_missing'] == 2
    assert len(result['eligible_rows']) == len(rows) - 2
    assert result['eligible_rows'].source_version.str.strip().ne('').all()

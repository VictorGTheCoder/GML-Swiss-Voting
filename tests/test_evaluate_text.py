from dataclasses import replace

import pandas as pd

from scripts.modeling.evaluate_votes import (
    EvaluationConfig,
    evaluate,
    synthetic_example,
)


def documents(rows):
    return [{"vote_id": r.vote_id, "voting_date": str(r.voting_date), "forecast_at": str(pd.Timestamp(r.forecast_at, tz="UTC")),
        "forecast_evidence": 'fixture release', "availability_at": str(pd.Timestamp(r.forecast_at, tz="UTC")),
        "availability_reference": 'fixture archive', "availability_status": 'CONFIRMED_PRE_VOTE',
        "source_sha256": 'fixture', "decision_source_sha256": 'fixture', "match_status": 'VALIDATED',
        "extraction_status": 'EXTRACTED', "semantic_status": 'VALIDATED',
        "language": 'fr', "summary_official": 'training apples oranges' if r.vote_id == 'old' else 'heldout bananas',
        "full_text": 'must not enter the model full text'}
        for r in rows.drop_duplicates('vote_id').itertuples()]


def test_text_comparison_is_paired_and_document_frequencies_count_objects():
    rows, config = synthetic_example()
    first = evaluate(rows, config, text_records=documents(rows))['text_experiment']
    assert first['status'] == 'evaluated'
    assert first['representation']['training_objects'] == ['old']
    assert 'bananas' not in first['representation']['vocabulary']
    assert first['representation']['idf'] == [1.] * len(first['representation']['vocabulary'])
    assert first['coverage']['paired']['rows'] == 2
    repeated = pd.concat([rows, rows.loc[rows.vote_id.eq('old')].assign(municipality_id=['d','e'])])
    second = evaluate(repeated, config, text_records=documents(rows))['text_experiment']
    assert first['representation'] == second['representation']
    keys = first['predictions'].groupby('model').apply(lambda g: set(zip(g.municipality_id,g.vote_id)),include_groups=False)
    assert keys.iloc[0] == keys.iloc[1]


def test_frozen_text_choices_and_predictions_ignore_test_targets():
    from scripts.modeling.final_evaluation import freeze_experiment
    rows, config = synthetic_example()
    records = documents(rows)
    frozen = freeze_experiment(evaluate(rows, config, text_records=records))
    config = replace(config, mode='final_test', choices_frozen=True,
        selected_ridge_alphas=frozen['selected_ridge_alphas'])
    first = evaluate(rows, config, text_records=records, frozen_experiment=frozen)['text_experiment']
    changed = rows.copy()
    changed.loc[changed.vote_id.eq('final'), ['yes_count','no_count']] = [1,99]
    second = evaluate(changed, config, text_records=records, frozen_experiment=frozen)['text_experiment']
    assert first['predictions'].prediction.tolist() == second['predictions'].prediction.tolist()
    assert first['models'] == second['models']
    assert first['models']['paired_text']['validation_scores_pp'] == {}


def test_real_eligibility_gates_and_cutoff_mismatch_skip_text_without_losing_nontext():
    rows, config = synthetic_example()
    for field, value in [('availability_status','INVESTIGATE'), ('decision_source_sha256','stale'),
                         ('forecast_at','2019-01-01')]:
        records = documents(rows)
        for record in records:
            record[field] = value
        result = evaluate(rows, config, text_records=records)
        assert result['text_experiment']['status'] == 'skipped'
        assert result['metrics']['municipal_history']['rows'] == 2
        assert result['text_experiment']['coverage']['lost_rows'] == 2
    records = documents(rows)
    records[1]['forecast_at'] = '2020-12-23T00:00:00Z'
    result = evaluate(rows, config, text_records=records)['text_experiment']
    assert result['forecast_or_date_mismatches'] == ['next']
    assert result['status'] == 'skipped'


def test_text_coverage_preserves_identical_keys_when_one_object_is_ineligible(tmp_path):
    from scripts.modeling.evaluate_votes import write_artifacts
    rows, config = synthetic_example()
    other = rows.loc[rows.vote_id.eq('next')].assign(vote_id='other')
    rows = pd.concat([rows, other], ignore_index=True)
    records = documents(rows)
    records[-1]['semantic_status'] = 'INVESTIGATE'
    result = evaluate(rows, config, text_records=records)
    experiment = result['text_experiment']
    assert experiment['coverage']['wider_nontext'] == {'rows':4,'objects':2,'dates':1}
    assert experiment['coverage']['paired'] == {'rows':2,'objects':1,'dates':1}
    assert experiment['metrics']['paired_nontext']['rows'] == experiment['metrics']['paired_text']['rows'] == 2
    write_artifacts(result, tmp_path)
    assert (tmp_path/'text_predictions.csv').exists()


def test_invalid_document_voting_date_is_an_auditable_mismatch():
    rows, config = synthetic_example()
    records = documents(rows)
    records[1]['voting_date'] = 'unknown'
    experiment = evaluate(rows, config, text_records=records)['text_experiment']
    assert experiment['status'] == 'skipped'
    assert experiment['forecast_or_date_mismatches'] == ['next']


def test_text_branch_uses_validated_official_summary_and_declares_tfidf_settings():
    rows, config = synthetic_example()
    records = documents(rows)
    records[0]['summary_official'] = 'apples oranges'
    records[0]['full_text'] = 'fulltextonly'
    records[1]['summary_official'] = 'heldout bananas'
    records[1]['full_text'] = 'futurefulltext'
    experiment = evaluate(rows, config, text_records=records)['text_experiment']

    assert experiment['status'] == 'evaluated'
    representation = experiment['representation']
    assert 'fulltextonly' not in representation['vocabulary']
    assert 'futurefulltext' not in representation['vocabulary']
    assert representation['settings']['ngram_range'] == [1, 2]
    assert representation['settings']['min_df'] == 2
    assert representation['settings']['max_df'] == 0.95
    assert representation['folds'][0]['max_df_adjustment'] == (
        'max_df increased to 1.0 because the proposed maximum-frequency cutoff '
        'is below the minimum-frequency cutoff for this training corpus')
    assert representation['settings']['max_features'] == 2000
    assert representation['language'] == 'fr'


def test_text_branch_skips_unresolved_language_without_suppressing_nontext():
    rows, config = synthetic_example()
    records = documents(rows)
    records[1]['language'] = 'de'
    result = evaluate(rows, config, text_records=records)

    assert result['text_experiment']['status'] == 'skipped'
    assert result['text_experiment']['reason'] == 'no selected-language summaries cover eligible evaluation objects'
    assert result['text_experiment']['language'] == 'fr'
    assert result['metrics']['municipal_history']['rows'] == 2


def test_text_branch_never_falls_back_to_full_text_when_summary_is_missing():
    rows, config = synthetic_example()
    records = documents(rows)
    for record in records:
        record['summary_official'] = None
        record['text'] = 'generic text must not be selected'
        record['full_text'] = 'full text must not be selected'
    experiment = evaluate(rows, config, text_records=records)['text_experiment']

    assert experiment['status'] == 'skipped'
    assert experiment['summary_status'] == 'prerequisite_unresolved'
    assert experiment['reason'] == 'no eligible validated official summaries are available'
    assert all('requested text field' in record['exclusion_reason'] for record in experiment['excluded_documents'])


def test_empty_summary_vocabulary_is_reported_and_only_skips_text():
    rows, config = synthetic_example()
    records = documents(rows)
    for record in records:
        record['summary_official'] = '!!!'
    result = evaluate(rows, config, text_records=records)

    assert result['text_experiment']['status'] == 'skipped'
    assert result['text_experiment']['windows'][0]['status'] == 'empty_vocabulary'
    assert 'no shared validation window' in result['text_experiment']['reason']
    assert result['metrics']['municipal_history']['rows'] == 2


def test_text_vocabulary_and_preprocessing_follow_shared_expanding_windows():
    rows = []
    for vote, date, available, shares in [
        ('train-a', '2020-01-01', '2020-01-02', [.2, .4]),
        ('train-b', '2021-01-01', '2022-02-01', [.3, .5]),
        ('valid-a', '2022-01-01', '2022-01-02', [.8, .6]),
        ('valid-b', '2023-01-01', '2023-01-02', [.9, .7]),
        ('test', '2024-01-01', '2024-01-02', [.1, .9]),
    ]:
        for municipality, share in zip(['a', 'b'], shares):
            rows.append({"municipality_id": municipality, "vote_id": vote, "voting_date": date,
                "yes_count": share*100, "no_count": (1-share)*100, "geography_id": 'g1',
                "source_version": 'fixture-v1', "result_available_at": available,
                "result_availability_evidence": 'fixture-result-release',
                "forecast_at": str(pd.Timestamp(date, tz='UTC')-pd.Timedelta(days=10)),
                "forecast_evidence": 'fixture-brochure', "is_special_unit": False,
                "is_subsidiary": False, "is_provisional": False})
    rows = pd.DataFrame(rows)
    config = EvaluationConfig(('2020-01-01', '2021-01-01'),
        ('2022-01-01', '2023-01-01'), ('2024-01-01',),
        validation_windows=(('2022-01-01',), ('2023-01-01',)), history_policy='rolling')
    records = documents(rows)
    summaries = {'train-a':'common alpha', 'train-b':'common beta paired',
        'valid-a':'interimword paired', 'valid-b':'futureword heldout', 'test':'testword'}
    for record in records:
        record['summary_official'] = summaries[record['vote_id']]
    result = evaluate(rows, config, text_records=records)['text_experiment']

    assert result['status'] == 'evaluated'
    assert [fold['training_objects'] for fold in result['windows']] == [
        ['train-a'], ['train-a', 'train-b', 'valid-a']]
    assert [fold['fit_cutoff'] for fold in result['windows']] == [
        '2020-01-02 00:00:00+00:00', '2022-02-01 00:00:00+00:00']
    assert 'futureword' not in result['windows'][0]['tfidf']['vocabulary']
    assert 'futureword' not in result['windows'][1]['tfidf']['vocabulary']
    assert result['windows'][0]['validation_row_keys'] == [['a', 'valid-a'], ['b', 'valid-a']]
    assert set(result['predictions'].validation_window) == {1, 2}
    for model in ('paired_nontext', 'paired_text'):
        assert result['models'][model]['refit_schedule'].startswith('one estimator and preprocessing fit')

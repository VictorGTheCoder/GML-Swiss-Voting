from dataclasses import replace
import pandas as pd
import pytest
from scripts.evaluate_votes import evaluate, synthetic_example


def documents(rows):
    return [dict(vote_id=r.vote_id, voting_date=str(r.voting_date), forecast_at=str(pd.Timestamp(r.forecast_at, tz="UTC")),
        forecast_evidence='fixture release', availability_at=str(pd.Timestamp(r.forecast_at, tz="UTC")),
        availability_reference='fixture archive', availability_status='CONFIRMED_PRE_VOTE',
        source_sha256='fixture', decision_source_sha256='fixture', match_status='VALIDATED',
        extraction_status='EXTRACTED', semantic_status='VALIDATED',
        text='training apples oranges' if r.vote_id == 'old' else 'heldout bananas')
        for r in rows.drop_duplicates('vote_id').itertuples()]


def test_text_comparison_is_paired_and_document_frequencies_count_objects():
    rows, config = synthetic_example()
    first = evaluate(rows, config, text_records=documents(rows))['text_experiment']
    assert first['status'] == 'evaluated'
    assert first['representation']['training_objects'] == ['old']
    assert 'bananas' not in first['representation']['vocabulary']
    assert first['representation']['idf'] == [1., 1., 1.]
    assert first['coverage']['paired']['rows'] == 2
    repeated = pd.concat([rows, rows.loc[rows.vote_id.eq('old')].assign(municipality_id=['d','e'])])
    second = evaluate(repeated, config, text_records=documents(rows))['text_experiment']
    assert first['representation'] == second['representation']
    keys = first['predictions'].groupby('model').apply(lambda g: set(zip(g.municipality_id,g.vote_id)),include_groups=False)
    assert keys.iloc[0] == keys.iloc[1]


def test_frozen_text_choices_and_predictions_ignore_test_targets():
    rows, config = synthetic_example()
    config = replace(config, mode='final_test', choices_frozen=True,
        selected_ridge_alphas={'paired_nontext':1.,'paired_text':1.})
    records = documents(rows)
    first = evaluate(rows, config, text_records=records)['text_experiment']
    changed = rows.copy()
    changed.loc[changed.vote_id.eq('final'), ['yes_count','no_count']] = [1,99]
    second = evaluate(changed, config, text_records=records)['text_experiment']
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
    from scripts.evaluate_votes import write_artifacts
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

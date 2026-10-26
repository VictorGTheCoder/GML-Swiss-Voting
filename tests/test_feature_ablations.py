from dataclasses import replace

import pandas as pd
import pytest

from scripts.modeling.evaluate_votes import evaluate, synthetic_example
from scripts.modeling.feature_blocks import synthetic_feature_example


def test_independent_ablation_reports_paired_keys_provenance_and_wider_coverage():
    rows, config = synthetic_example()
    first = synthetic_feature_example()
    second = replace(first, block_id='second')
    result = evaluate(rows, config, feature_blocks=(first, second))
    reports = result['ablations']
    report = reports[first.block_id]
    assert report['compared_row_keys'] == [['a','next'],['c','next']]
    assert report['paired_rows'] == 2
    assert report['wider_nontext_coverage']['rows'] == 2
    assert report['source_version'] == 'synthetic-statpop-v1'
    assert all('second__' not in name for name in report['features'])
    assert report['paired_mae_change_pp'] == pytest.approx(
        result['metrics']['ridge_statpop_nationality']['mae_pp'] - result['metrics']['ridge_history']['mae_pp'])
    assert evaluate(rows, config, feature_blocks=(first, second))['ablations'] == reports


def test_unavailable_source_skips_without_blocking_other_independent_experiments():
    rows, config = synthetic_example()
    available = synthetic_feature_example()
    missing = replace(available, block_id='party_strength', records=pd.DataFrame(),
                      prerequisite_reason='Historical release archive not prepared')
    result = evaluate(rows, config, feature_blocks=(available, missing))
    assert result['ablations']['party_strength']['status'] == 'skipped'
    assert result['ablations']['party_strength']['prerequisite_reason'] == 'Historical release archive not prepared'
    assert result['ablations']['party_strength']['compared_row_keys'] == []
    assert 'ridge_party_strength' not in result['metrics']
    assert result['ablations']['statpop_nationality']['status'] == 'completed'


@pytest.mark.parametrize('outcome', ['ballots_cast','valid_ballots','blank_invalid_ballots','yes_pct_ofs','turnout_pct_ofs'])
def test_canonical_outcome_fields_are_rejected_as_metadata_predictors(outcome):
    rows, config = synthetic_example()
    source = synthetic_feature_example()
    unsafe = replace(source, numeric_features=(outcome,), definitions={outcome:'unsafe target-object field'},
                     records=source.records.assign(**{outcome: 1}))
    with pytest.raises(ValueError, match='outcome'):
        evaluate(rows, config, feature_blocks=(unsafe,))


def test_object_metadata_requires_validated_correspondence_and_timely_release():
    rows, config = synthetic_example()
    source = synthetic_feature_example()
    records = pd.DataFrame([dict(vote_id=vote, reference_date='2018-01-01', published_at='2019-01-01',
        availability_status='verified',availability_evidence='fixture-release',source_version=source.source_version,
        legal_type='law') for vote in ['old','next','final']])
    metadata = replace(source, block_id='legal', scope='object', records=records,
                       numeric_features=(),categorical_features=('legal_type',),definitions={'legal_type':'legal instrument'})
    with pytest.raises(ValueError, match='correspondence'):
        evaluate(rows,config,feature_blocks=(metadata,))
    records['object_match_status'] = 'validated'
    records['object_match_evidence'] = 'reviewed-fixture-link'
    records.loc[records.vote_id.eq('next'),'published_at'] = '2020-12-25'
    result = evaluate(rows,config,feature_blocks=(replace(metadata,records=records),))
    assert result['joined_features'].query("vote_id == 'next'").legal__legal_type.isna().all()
    assert result['ablations']['legal']['paired_rows'] == 2
    assert result['ablations']['legal']['missingness_and_join_losses']['unavailable_at_forecast_rows'] == 2

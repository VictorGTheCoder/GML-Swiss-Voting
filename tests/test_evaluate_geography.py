import pandas as pd
import pytest

from scripts.evaluate_votes import EvaluationConfig, evaluate


def record(municipality, vote, date, yes, no, geography):
    return dict(municipality_id=municipality, vote_id=vote, voting_date=date, yes_count=yes,
                no_count=no, geography_id=geography, source_version='fixture-v1',
                result_available_at=date, result_availability_evidence='fixture-result',
                forecast_at=str(pd.Timestamp(date)-pd.Timedelta(days=10)), forecast_evidence='fixture-brochure',
                is_special_unit=False, is_subsidiary=False, is_provisional=False)


def population():
    return pd.DataFrame([record('a','old','2020-01-01',20,80,'old'),
                         record('b','old','2020-01-01',90,210,'old'),
                         record('ab','next','2021-01-01',80,120,'new'),
                         record('ab','final','2022-01-01',90,110,'new')])


def configuration(**changes):
    return EvaluationConfig(('2020-01-01',), ('2021-01-01',), ('2022-01-01',), **changes)


def crosswalk():
    return pd.DataFrame([dict(source_municipality_id=key, source_geography_id='old',
        target_municipality_id='ab', target_geography_id='new', mapping_type='merger',
        crosswalk_version='cw-v1', crosswalk_evidence='official-reference',
        mapping_available_at='2019-01-01', target_valid_from='2019-01-01') for key in ['a','b']])


def test_pipeline_aggregates_merger_counts_and_records_lineage():
    result = evaluate(population(), configuration(), geography_crosswalk=crosswalk())
    old = result['eligible_rows'].query("vote_id == 'old'").iloc[0]
    assert old.yes_count == 110
    assert old.no_count == 290
    assert old.target_share == pytest.approx(.275)
    assert len(result['eligible_rows']) == 3
    assert result['predictions'].prediction.tolist() == pytest.approx([.275,.275])
    assert result['metrics']['municipal_history']['mae_pp'] == pytest.approx(12.5)
    assert result['coverage']['municipal_history']['fallback_rows'] == 0
    assert result['manifest']['geography']['crosswalk_versions'] == ['cw-v1']
    assert result['manifest']['geography']['input_references'] == ['new','old']
    assert old.source_municipalities == 'a|b'


def test_unsupported_splits_and_missing_mappings_are_excluded_not_multiplied():
    data = pd.concat([population(), pd.DataFrame([record('x','old','2020-01-01',40,60,'old'),
                                                  record('z','old','2020-01-01',50,50,'old')])], ignore_index=True)
    mapping = pd.concat([crosswalk(), pd.DataFrame([crosswalk().iloc[0].to_dict() | dict(
        source_municipality_id='x',target_municipality_id=target,mapping_type='split') for target in ['x1','x2']])], ignore_index=True)
    result = evaluate(data, configuration(), geography_crosswalk=mapping)
    assert result['exclusions']['unsupported_geography_mapping'] == 1
    assert result['exclusions']['geography_mapping_missing'] == 1
    assert len(result['eligible_rows']) == 3
    assert result['predictions'].prediction.tolist() == pytest.approx([.275,.275])


@pytest.mark.parametrize('problem', ['duplicate_mapping', 'already_harmonized', 'mixed_target'])
def test_ambiguous_cardinality_and_double_harmonization_fail_closed(problem):
    data, mapping = population(), crosswalk()
    if problem == 'duplicate_mapping':
        mapping = pd.concat([mapping, mapping.iloc[[0]]], ignore_index=True)
    elif problem == 'already_harmonized':
        data['harmonization_applied'] = True
    else:
        data = pd.concat([data,pd.DataFrame([record('ab','old','2020-01-01',1,99,'new')])], ignore_index=True)
    with pytest.raises(ValueError, match='cardinality|harmoniz|overlap'):
        evaluate(data, configuration(), geography_crosswalk=mapping)


def test_mapping_availability_and_territorial_lifetimes_distinguish_modes():
    mapping = crosswalk()
    mapping['mapping_available_at'] = '2021-06-01'
    strict = evaluate(population(), configuration(), geography_crosswalk=mapping)
    retrospective = evaluate(population(), configuration(geography_mode='retrospective_fixed'), geography_crosswalk=mapping)
    assert strict['exclusions']['geography_mapping_unavailable'] == 2
    assert strict['predictions'].empty
    assert retrospective['predictions'].prediction.tolist() == pytest.approx([.275,.275])
    assert retrospective['manifest']['geography']['mode'] == 'retrospective_fixed'
    mapping['mapping_available_at'] = '2019-01-01'
    mapping['target_valid_to'] = '2020-06-01'
    strict = evaluate(population(), configuration(), geography_crosswalk=mapping)
    assert strict['exclusions']['target_not_existing_at_forecast'] == 2
    assert strict['predictions'].empty


def test_incomplete_merger_does_not_silently_change_territory():
    data = population().loc[lambda df: df.municipality_id.ne('b')]
    result = evaluate(data, configuration(), geography_crosswalk=crosswalk())
    assert result['exclusions']['incomplete_geography_merger'] == 1
    assert result['predictions'].empty
    mapping = crosswalk()
    mapping.loc[0, 'crosswalk_evidence'] = None
    result = evaluate(population(), configuration(), geography_crosswalk=mapping)
    assert result['exclusions']['geography_evidence_missing'] == 1
    assert result['exclusions']['incomplete_geography_merger'] == 1


def test_prepared_harmonization_preserves_provenance_and_missing_result_evidence():
    data = population()
    data.loc[0, 'result_availability_evidence'] = ''
    result = evaluate(data, configuration(), geography_crosswalk=crosswalk())
    assert result['predictions'].empty
    harmonized = evaluate(population(), configuration(), geography_crosswalk=crosswalk())['eligible_rows']
    rerun = evaluate(harmonized, configuration())
    assert rerun['manifest']['geography']['crosswalk_versions'] == ['cw-v1']
    with pytest.raises(ValueError, match='provenance'):
        evaluate(harmonized.drop(columns='crosswalk_evidence'), configuration())

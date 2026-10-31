"""Integration against the current source pipeline's public Parquet contracts."""
import hashlib

import pandas as pd
import pytest

from scripts.integration.modeling_objects import build_object_feature_block
from scripts.integration.modeling_v1 import prepare_v1_table, write_v1_artifacts
from scripts.integration.modeling_v1_sources import GEOGRAPHY_ID, load_processed_v1_sources


def write_sources(root):
    sources = {
        'statpop/statpop_features': pd.DataFrame([
            {'municipality_id': '0001', 'year': 2010, 'pop_total': 100,
             'share_foreign': .2, 'share_0_19': .25, 'share_20_39': .3,
             'share_65_plus': .15, 'available_from': '2011-09-02'},
        ]),
        'typologies/commune_typologies': pd.DataFrame([
            {'municipality_id': '0001', 'canton': 'VD', 'language_region': '2', 'urban_rural': '3'},
        ]),
        'swissvotes/swissvotes_clean': pd.DataFrame([
            {'swissvotes_id': '1', 'vote_date': pd.Timestamp('2012-03-04'), 'rechtsform': '1',
             'd1e1': '1', 'd2e1': '2', 'd3e1': '1', 'vote_key': '10'},
        ]),
    }
    for name, rows in sources.items():
        path = root / 'processed' / f'{name}.parquet'
        path.parent.mkdir(parents=True, exist_ok=True)
        rows.to_parquet(path, index=False)
    return sources


def test_current_sources_prepare_reproducibly_without_promoting_assumed_publication(tmp_path):
    write_sources(tmp_path)
    paths = sorted(tmp_path.rglob('*.parquet'))
    before = {p: p.read_bytes() for p in paths}
    outcomes = pd.DataFrame([
        {'municipality_id': '0001', 'vote_id': '10', 'vote_date': '2012-03-04',
         'votes_yes': 30, 'votes_no': 70, 'is_special_unit': False,
         'is_tiebreak_question': False, 'is_provisional': False},
    ])
    for name in ('first', 'second'):
        blocks, swiss, audit = load_processed_v1_sources(tmp_path, geography_id=GEOGRAPHY_ID)
        objects = build_object_feature_block(outcomes, swiss.records, source_version=swiss.source_version)
        assert objects.join_audit.join_status.tolist() == ['matched']
        result = prepare_v1_table(outcomes, geography_id=GEOGRAPHY_ID,
                                  source_version='fixture-outcomes', municipal_blocks=blocks,
                                  object_features=objects, source_audit=audit)
        row = result.prepared.iloc[0]
        assert row.target_share == .3
        assert row.population_total == 100
        assert row.share_age_20_39 == .3
        assert row.urban_rural_type == 'rural'
        assert row.language_region == '2'
        assert row.policy_domain_01 == row.policy_domain_02 == 1
        assert len(result.candidate_columns) == 30
        assert result.strict_population.empty
        assert result.readiness['modeling_ready'] is False
        assert blocks[0].records.published_at.isna().all()
        assert blocks[0].records.availability_status.eq('unknown').all()
        assert audit['statpop']['sha256'] == hashlib.sha256(before[paths[0]]).hexdigest()
        write_v1_artifacts(result, tmp_path / name)
    for path in (tmp_path / 'first').iterdir():
        assert path.read_bytes() == (tmp_path / 'second' / path.name).read_bytes()
    assert before == {p: p.read_bytes() for p in paths}


def test_current_source_adapter_rejects_wrong_geography_and_duplicate_release(tmp_path):
    sources = write_sources(tmp_path)
    with pytest.raises(ValueError, match='geography_id'):
        load_processed_v1_sources(tmp_path, geography_id='historical-2012')
    population = sources['statpop/statpop_features']
    pd.concat([population, population]).to_parquet(
        tmp_path / 'processed/statpop/statpop_features.parquet', index=False)
    with pytest.raises(ValueError, match='duplicate'):
        load_processed_v1_sources(tmp_path, geography_id=GEOGRAPHY_ID)

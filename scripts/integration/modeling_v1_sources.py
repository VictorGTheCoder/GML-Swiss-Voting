"""Adapt main's source snapshots to V1 without inventing release evidence.

These inputs are already harmonized to 2026. Their hashes identify the actual
prepared bytes; available_from is an exploratory assumption, never publication
proof. The legacy raw-source adapters remain available separately.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from scripts.integration.modeling_municipal import normalize_municipality_id
from scripts.integration.modeling_objects import SwissvotesSource
from scripts.modeling.feature_blocks import FeatureBlock

GEOGRAPHY_ID = 'bfs-2026-01-01'
DEMOGRAPHICS = {
    'pop_total': 'population_total', 'share_foreign': 'share_foreign',
    'share_0_19': 'share_age_0_19', 'share_20_39': 'share_age_20_39',
    'share_65_plus': 'share_age_65_plus',
}


def load_processed_v1_sources(data_root: Path, *, geography_id: str):
    """Load the established source tables; return blocks, Swissvotes and audit.

    The fixed snapshot geography is a checked precondition, not a user-selected
    label for arbitrary territories. No crosswalk is applied a second time.
    """
    if geography_id != GEOGRAPHY_ID:
        raise ValueError(f'Processed V1 sources require geography_id={GEOGRAPHY_ID}')
    root = Path(data_root) / 'processed'
    paths = {
        'statpop': root / 'statpop/statpop_features.parquet',
        'territory': root / 'typologies/commune_typologies.parquet',
        'swissvotes': root / 'swissvotes/swissvotes_clean.parquet',
    }
    frames, audit = {}, {}
    for name, path in paths.items():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        frames[name] = pd.read_parquet(path)
        audit[name] = {'path': path.relative_to(data_root).as_posix(),
                       'sha256': digest, 'source_version': f'sha256:{digest}'}
    population = frames['statpop'].rename(columns=DEMOGRAPHICS).copy()
    population = population.loc[population.year.between(2010, 2025)]
    population['reference_date'] = population.year.astype(str) + '-12-31'
    territory = frames['territory'].copy()
    territory['urban_rural_type'] = territory.urban_rural.astype('string').map(
        {'1': 'urban', '2': 'intermediate', '3': 'rural'})
    territory['reference_date'] = '2026-01-01'
    blocks = []
    specs = [
        ('statpop', 'municipal_demography', population, tuple(DEMOGRAPHICS.values()), (),
         'https://www.pxweb.bfs.admin.ch/'),
        ('territory', 'municipal_context', territory, (),
         ('canton', 'language_region', 'urban_rural_type'),
         'https://www.agvchapp.bfs.admin.ch/fr/typologies/query'),
    ]
    for source, block_id, records, numeric, categorical, url in specs:
        records['municipality_id'] = normalize_municipality_id(records.municipality_id)
        if records.municipality_id.isna().any() or records.duplicated(['municipality_id', 'reference_date']).any():
            raise ValueError(f'{source}: null or duplicate municipal release keys')
        records['geography_id'] = geography_id
        records['published_at'] = None
        records['availability_status'] = 'unknown'
        records['availability_evidence'] = None
        records['source_version'] = audit[source]['source_version']
        columns = ['municipality_id', 'geography_id', 'reference_date', 'published_at',
                   'availability_status', 'availability_evidence', 'source_version', *numeric, *categorical]
        definitions = {name: ('Permanent resident population' if name == 'population_total'
                             else 'Share of total permanent resident population' if name.startswith('share_')
                             else 'Nominal OFS territorial classification') for name in (*numeric, *categorical)}
        blocks.append(FeatureBlock(
            block_id=block_id, scope='municipality', records=records[columns].copy(),
            numeric_features=numeric, categorical_features=categorical, definitions=definitions,
            source_url=url, source_version=audit[source]['source_version'],
            geography_mode='retrospective_fixed'))
    swiss = frames['swissvotes'].rename(columns={'swissvotes_id': 'anr', 'vote_date': 'datum'})
    source = SwissvotesSource(records=swiss, source_version=audit['swissvotes']['source_version'],
                             source_url='https://swissvotes.ch/page/dataset', retrieved_at='',
                             sha256=audit['swissvotes']['sha256'])
    audit['geography'] = {'reference': geography_id, 'mode': 'retrospective_fixed',
                          'harmonization': 'already applied by source pipelines; no second crosswalk'}
    audit['publication_evidence'] = 'unknown; available_from is not historical version evidence'
    return tuple(blocks), source, audit

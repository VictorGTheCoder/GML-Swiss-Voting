"""Prepare measured census ages and annual STATPOP ages, with explicit selection assumptions."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.common.config import ROOT
from scripts.espop.audit_reuse import harmonize_counts, read_census, snapshot, verify_manifest
from scripts.espop.population_history import DEFAULT_REUSE
from scripts.modeling.retrospective_demo import sha256
from scripts.repertoire_communes.commune_crosswalk import load_mutations

CENSUS_DATES = {1980: '1980-12-02', 1990: '1990-12-04', 2000: '2000-12-05'}
GROUPS = ('0_19', '20_39', '65_plus')
AGE_SHARES = [f'age_share_{group}' for group in GROUPS]
DEFAULT_OUTPUT = ROOT / 'data/interim/census_age_history'


def prepare_releases(censuses, source_codes, target_codes, mutations, statpop):
    """Keep exclusions as explicit releases so joins cannot conceal a failed new census."""
    if set(censuses) != set(CENSUS_DATES):
        raise ValueError('Expected the three censuses 1980, 1990 and 2000')
    targets = sorted(str(c).zfill(4) for c in target_codes)
    releases, exclusions = [], []
    for year, day in CENSUS_DATES.items():
        census = censuses[year]
        if not census.year.eq(year).all():
            raise ValueError('Census year mismatch')
        mapped, excluded = harmonize_counts(census, source_codes[year], target_codes,
                                             date.fromisoformat(day), date(2026, 1, 1), mutations)
        exclusions.append(excluded.assign(census_year=year))
        mapped['municipality_id'] = mapped.code.astype('string').str.zfill(4)
        frame = pd.DataFrame({'municipality_id': targets}).merge(
            mapped, on='municipality_id', how='left', validate='one_to_one')
        frame['age_reference_year'] = year
        frame['age_reference_date'] = pd.Timestamp(day)
        frame['age_selection_from'] = pd.Timestamp(f'{year + 3}-01-01')
        frame['age_source'] = 'RFP'
        frame['age_population_definition'] = 'census_resident_population'
        frame['age_denominator'] = pd.to_numeric(frame.population, errors='coerce')
        for group in GROUPS:
            frame[f'age_count_{group}'] = pd.to_numeric(frame[f'age_{group}'], errors='coerce')
        releases.append(frame)
    # Retain an explicit annual record even if a stock is missing or invalid.
    expected = pd.MultiIndex.from_product([range(2010, 2022), targets],
                                          names=['year', 'municipality_id'])
    stats = statpop.loc[statpop.year.between(2010, 2021)].copy()
    if stats.duplicated(['year', 'municipality_id']).any():
        raise ValueError('Duplicate annual STATPOP age keys')
    stats = stats.set_index(['year', 'municipality_id']).reindex(expected).reset_index()
    stats['age_reference_year'] = stats.year
    stats['age_reference_date'] = pd.to_datetime(stats.year.astype(str) + '-12-31')
    stats['age_selection_from'] = pd.to_datetime((stats.year + 1).astype(str) + '-09-02')
    stats['age_source'] = 'STATPOP'
    stats['age_population_definition'] = 'permanent_resident_population'
    stats['age_denominator'] = stats.pop_total
    for group in GROUPS:
        stats[f'age_count_{group}'] = stats[f'pop_{group}']
    releases.append(stats)
    columns = ['municipality_id', 'age_reference_year', 'age_reference_date', 'age_selection_from',
               'age_source', 'age_population_definition', 'age_denominator'] + [f'age_count_{g}' for g in GROUPS]
    result = pd.concat([frame[columns] for frame in releases], ignore_index=True)
    counts = result[[f'age_count_{g}' for g in GROUPS]]
    valid = (np.isfinite(result.age_denominator) & result.age_denominator.gt(0)
             & np.isfinite(counts).all(axis=1) & counts.ge(0).all(axis=1)
             & counts.sum(axis=1).le(result.age_denominator))
    result['age_valid'] = valid
    result['age_missing_reason'] = np.where(valid, '', 'unresolved_geography_or_invalid_age_counts')
    for group in GROUPS:
        result[f'age_share_{group}'] = (result[f'age_count_{group}'] /
                                         result.age_denominator.where(valid)).where(valid)
    result['historical_availability'] = 'unverified_retrospective_selection_rule'
    if result.duplicated(['municipality_id', 'age_selection_from']).any():
        raise ValueError('Duplicate age selection keys')
    return result.sort_values(['age_selection_from', 'municipality_id']).reset_index(drop=True), pd.concat(exclusions)


def run(reference_dir=DEFAULT_REUSE, output=DEFAULT_OUTPUT, root=ROOT):
    reference_dir, output, root = map(Path, [reference_dir, output, root])
    source_manifest = verify_manifest(reference_dir)
    required = {'census.xlsx', 'mutations.csv', 'snapshot_2026-01-01.csv',
                *[f'snapshot_{day}.csv' for day in CENSUS_DATES.values()]}
    if not required <= {source['file'] for source in source_manifest['sources']}:
        raise ValueError('Missing manifested census or geographical sources')
    statpop_path = root / 'data/processed/statpop/statpop_features.parquet'
    statpop = pd.read_parquet(statpop_path, filters=[('year', '<=', 2021)],
                              columns=['year', 'municipality_id', 'pop_total'] + [f'pop_{g}' for g in GROUPS])
    censuses = {y: read_census(reference_dir / 'census.xlsx', y) for y in CENSUS_DATES}
    sources = {y: snapshot(reference_dir, day) for y, day in CENSUS_DATES.items()}
    releases, exclusions = prepare_releases(censuses, sources, snapshot(reference_dir, '2026-01-01'),
                                             load_mutations(reference_dir / 'mutations.csv'), statpop)
    coverage = releases.groupby(['age_source', 'age_reference_year'], as_index=False).agg(
        rows=('municipality_id', 'size'), valid_rows=('age_valid', 'sum'))
    output.mkdir(parents=True, exist_ok=True)
    releases.to_parquet(output / 'age_releases.parquet', index=False)
    exclusions.to_csv(output / 'geography_exclusions.csv', index=False)
    coverage.to_csv(output / 'release_coverage.csv', index=False)
    manifest = {'mode': 'exploratory_retrospective', 'strict_forecast_ready': False,
                'census_dates': CENSUS_DATES, 'census_selection_rule': '1 January Y+3; assumption, not publication evidence',
                'statpop_selection_rule': '2 September Y+1; assumption, not publication evidence',
                'shares': AGE_SHARES, 'sources': source_manifest,
                'statpop_sha256': sha256(statpop_path), 'geography': 'retrospective_fixed_2026-01-01',
                'age_releases_sha256': sha256(output / 'age_releases.parquet'),
                'geography_excluded_rows': len(exclusions),
                'implementation_sha256': {p.name: sha256(p) for p in [Path(__file__),
                                         root / 'scripts/espop/audit_reuse.py',
                                         root / 'scripts/repertoire_communes/commune_crosswalk.py']}}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    print(coverage.to_string(index=False))
    return releases, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-dir', type=Path, default=DEFAULT_REUSE)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    run(args.reference_dir, args.output)


if __name__ == '__main__':
    main()

"""Prepare an isolated annual ESPOP/STATPOP history from verified official counts."""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from scripts.common.config import ROOT
from scripts.espop.audit_reuse import harmonize_counts, read_cube, snapshot, verify_manifest
from scripts.espop.collect_reuse import BALANCE_URL
from scripts.modeling.retrospective_demo import sha256
from scripts.repertoire_communes.commune_crosswalk import load_mutations

YEARS = tuple(range(1981, 2010))
DEFAULT_RAW = ROOT / 'data/raw/espop_training_1981_2009'
DEFAULT_REUSE = ROOT / 'data/raw/espop_reuse/issue67_2026-10-31'
DEFAULT_OUTPUT = ROOT / 'data/interim/population_history'


def collect(raw_dir, reference_dir):
    """Cache full official annual counts with requests, response hashes and collection dates."""
    raw_dir, reference_dir = Path(raw_dir), Path(reference_dir)
    if (raw_dir / 'manifest.json').exists():
        return verify_manifest(raw_dir)
    if raw_dir.exists() and any(raw_dir.iterdir()):
        raise ValueError('Unmanifested partial collection; use a new raw directory')
    raw_dir.mkdir(parents=True, exist_ok=True)
    reference = json.loads((reference_dir / 'balance_metadata.json').read_text())
    response = requests.get(BALANCE_URL, timeout=60)
    response.raise_for_status()
    metadata = response.json()
    # Old geographical evidence must still describe the requested current cube.
    if metadata['variables'] != reference['variables']:
        raise ValueError('Official cube dimensions changed; reassess the pinned territorial reference')
    sources = []

    def archive(name, response, query=None):
        response.raise_for_status()
        path = raw_dir / name
        path.write_bytes(response.content)
        sources.append({'file': name, 'url': response.url, 'query': query,
                        'retrieved_at_utc': datetime.now(timezone.utc).isoformat(), 'sha256': sha256(path),
                        'bytes': len(response.content), 'historical_availability': 'not_proven',
                        'territorial_reference': '2025-04-06 plus unresolved legacy codes'})

    archive('metadata.json', response)
    variables = metadata['variables']
    communes = [key for key, label in zip(variables[1]['values'], variables[1]['valueTexts'])
                if label.startswith('......')]
    for start in range(1981, 2010, 5):
        years = [str(y) for y in range(start, min(start + 5, 2010))]
        selections = [years, communes, ['0', '2'], ['0'], ['16']]
        query = {'query': [{'code': var['code'], 'selection': {'filter': 'item', 'values': selected}}
                           for var, selected in zip(variables, selections)], 'response': {'format': 'csv'}}
        response = requests.post(BALANCE_URL, json=query, timeout=60)
        archive(f'balance_{years[0]}_{years[-1]}.csv', response, query)
        print(f'Collected official stocks {years[0]}–{years[-1]}', flush=True)
    manifest = {'purpose': 'Isolated retrospective population-history training experiment', 'sources': sources}
    (raw_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    return manifest


def prepare_population(counts, statpop, source_codes, target_codes, mutations):
    """Aggregate counts before ratios; retain invalid annual releases as explicit missing rows."""
    if counts.duplicated(['year', 'code']).any() or set(counts.year) != set(YEARS):
        raise ValueError('Expected unique annual official counts covering 1981–2009')
    mapped, exclusions = harmonize_counts(counts, source_codes, target_codes,
                                          date(2025, 4, 6), date(2026, 1, 1), mutations)
    es = mapped.rename(columns={'code': 'municipality_id'})
    es['municipality_id'] = es.municipality_id.astype('string').str.zfill(4)
    es = es[['year', 'municipality_id', 'population', 'foreign']]
    stats = statpop.loc[statpop.year.between(2010, 2021),
                        ['year', 'municipality_id', 'pop_total', 'pop_foreign']].rename(
        columns={'pop_total': 'population', 'pop_foreign': 'foreign'})
    expected = pd.MultiIndex.from_product([range(1981, 2022), sorted(str(c).zfill(4) for c in target_codes)],
                                          names=['year', 'municipality_id'])
    series = pd.concat([es, stats], ignore_index=True)
    if series.duplicated(['year', 'municipality_id']).any():
        raise ValueError('Population source-year overlap or duplicate keys')
    series = series.set_index(['year', 'municipality_id']).reindex(expected).reset_index()
    series['population_source'] = np.where(series.year.lt(2010), 'ESPOP_balance', 'STATPOP')
    series['population_reference_date'] = pd.to_datetime(series.year.astype(str) + '-12-31')
    # Explicit retrospective assumption, not a certified publication instant.
    series['population_selection_from'] = pd.to_datetime((series.year + 1).astype(str) + '-09-02')
    valid = (np.isfinite(series.population) & np.isfinite(series.foreign) & series.population.gt(0)
             & series.foreign.ge(0) & series.foreign.le(series.population))
    series['population_valid'] = valid
    series['population_missing_reason'] = np.where(valid, '', 'missing_nonpositive_or_invalid_stock')
    series['population_total'] = series.population.where(valid)
    series['population_share_foreign'] = (series.foreign / series.population.where(valid)).where(valid)
    series['historical_availability'] = 'unverified_retrospective_selection_rule'
    return series, exclusions


def run(raw_dir=DEFAULT_RAW, reference_dir=DEFAULT_REUSE, output=DEFAULT_OUTPUT, root=ROOT):
    raw_dir, reference_dir, output, root = map(Path, [raw_dir, reference_dir, output, root])
    reuse_manifest = verify_manifest(reference_dir)
    manifest = collect(raw_dir, reference_dir)
    counts = pd.concat([read_cube(raw_dir / s['file']) for s in manifest['sources']
                        if s['file'].startswith('balance_')], ignore_index=True)
    checkpoint = read_cube(reference_dir / 'balance.csv')
    compared = counts.merge(checkpoint, on=['year', 'code'], suffixes=('', '_audit'),
                            validate='one_to_one', how='inner')
    expected_checkpoints = checkpoint.loc[checkpoint.year.isin(YEARS)]
    if expected_checkpoints.empty or len(compared) != len(expected_checkpoints) or not (compared.population.eq(compared.population_audit)
                                        & compared.foreign.eq(compared.foreign_audit)).all():
        raise ValueError('The complete official extraction disagrees with the four pinned audit years')
    statpop_path = root / 'data/processed/statpop/statpop_features.parquet'
    statpop = pd.read_parquet(statpop_path, filters=[('year', '<=', 2021)])
    mutations = load_mutations(reference_dir / 'mutations.csv')
    source_codes = snapshot(reference_dir, '2025-04-06')
    target_codes = snapshot(reference_dir, '2026-01-01')
    population, exclusions = prepare_population(counts, statpop, source_codes, target_codes, mutations)
    output.mkdir(parents=True, exist_ok=True)
    population.to_parquet(output / 'annual_population.parquet', index=False)
    exclusions.to_csv(output / 'geography_exclusions.csv', index=False)
    coverage = population.groupby(['year', 'population_source'], as_index=False).agg(
        rows=('municipality_id', 'size'), valid_stocks=('population_valid', 'sum'))
    coverage.to_csv(output / 'annual_coverage.csv', index=False)
    result = {'mode': 'exploratory_retrospective', 'strict_forecast_ready': False,
              'requested_years': [1981, 2021], 'espop_years': [1981, 2009], 'statpop_years': [2010, 2021],
              'selection_rule': '2 September Y+1; retrospective assumption, not publication evidence',
              'geography': 'retrospective_fixed_2026-01-01', 'official_collection': manifest,
              'reference_collection': reuse_manifest, 'reference_directory': str(reference_dir),
              'raw_directory': str(raw_dir), 'statpop_sha256': sha256(statpop_path),
              'geography_excluded_rows': len(exclusions), 'valid_annual_stocks': int(population.population_valid.sum()),
              'official_audit_checkpoint_rows_equal': len(compared),
              'annual_population_sha256': sha256(output / 'annual_population.parquet'),
              'implementation_sha256': sha256(Path(__file__)),
              'harmonizer_sha256': sha256(root / 'scripts/espop/audit_reuse.py')}
    (output / 'manifest.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(coverage.to_string(index=False))
    return population, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-dir', type=Path, default=DEFAULT_RAW)
    parser.add_argument('--reference-dir', type=Path, default=DEFAULT_REUSE)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    run(args.raw_dir, args.reference_dir, args.output)


if __name__ == '__main__':
    main()

"""Publication-aware municipal evaluation; see docs/project/municipal_evaluation.md."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import platform

import numpy as np
import pandas as pd

KEYS = ['municipality_id', 'vote_id']
FLAGS = ['is_special_unit', 'is_subsidiary', 'is_provisional']
REQUIRED = KEYS + ['voting_date', 'yes_count', 'no_count', 'geography_id', 'source_version',
                   'result_available_at', 'result_availability_evidence', 'forecast_at',
                   'forecast_evidence'] + FLAGS


@dataclass(frozen=True)
class EvaluationConfig:
    train_dates: tuple[str, ...]
    validation_dates: tuple[str, ...]
    test_dates: tuple[str, ...]
    history_policy: str = 'frozen'
    mode: str = 'validation'
    seed: int = 0
    choices_frozen: bool = False
    predictor_allowlist: tuple[str, ...] = ('municipal_history', 'history_missing')
    geography_mode: str = 'historically_existing'
    audit_flag_policy: str = 'exclude'


def evaluate(prepared: pd.DataFrame, config: EvaluationConfig) -> dict:
    """Run the complete evaluation seam on prepared rows, returning auditable artifacts."""
    missing = set(REQUIRED) - set(prepared.columns)
    if missing:
        raise ValueError(f'Missing prepared columns: {sorted(missing)}')
    date_groups = [pd.to_datetime(list(dates), utc=True) for dates in
                   [config.train_dates, config.validation_dates, config.test_dates]]
    all_dates = [date for group in date_groups for date in group]
    if len(all_dates) != len(set(all_dates)):
        raise ValueError('Partition dates must be disjoint and unique')
    if any(len(group) == 0 for group in date_groups):
        raise ValueError('All three date partitions must be declared')
    if not (max(date_groups[0]) < min(date_groups[1]) and max(date_groups[1]) < min(date_groups[2])):
        raise ValueError('Partitions must be chronological')
    if config.history_policy not in ['frozen', 'rolling']:
        raise ValueError('Invalid history_policy')
    if config.mode not in ['validation', 'final_test']:
        raise ValueError('Invalid evaluation mode')
    if config.mode == 'final_test' and not config.choices_frozen:
        raise ValueError('Final test requires frozen choices')
    if config.geography_mode not in ['historically_existing', 'retrospective_fixed']:
        raise ValueError('Invalid geography_mode')
    if config.audit_flag_policy != 'exclude':
        raise ValueError('audit_flag_policy must explicitly exclude flagged rows')
    if set(config.predictor_allowlist) != {'municipal_history', 'history_missing'}:
        raise ValueError('Baseline predictor allowlist must contain only municipal_history and history_missing')
    rows = prepared.copy()
    exclusions = {}
    def exclude(mask, reason):
        nonlocal rows
        count = int(mask.fillna(True).sum())
        if count:
            exclusions[reason] = count
            rows = rows.loc[~mask.fillna(True)].copy()
    exclude(rows[KEYS].isna().any(axis=1), 'missing_key')
    for key in KEYS:
        rows[key] = rows[key].astype(str)
    exclude(rows.duplicated(KEYS, keep=False), 'duplicate_key')
    for flag in FLAGS:
        exclude(~rows[flag].isin([True, False]), 'ambiguous_' + flag)
        exclude(rows[flag].eq(True), flag.removeprefix('is_'))
    for name in sorted(c for c in rows.columns if c.startswith('flag_')):
        exclude(rows[name].fillna(True).ne(False), 'audit_' + name)
    for name in ['yes_count', 'no_count']:
        rows[name] = pd.to_numeric(rows[name], errors='coerce')
    total = rows.yes_count + rows.no_count
    exclude(~(np.isfinite(rows.yes_count) & np.isfinite(rows.no_count)
              & rows.yes_count.ge(0) & rows.no_count.ge(0) & total.gt(0)), 'undefined_target')
    exclude(rows.geography_id.isna() | rows.geography_id.astype(str).str.strip().eq(''), 'geography_missing')
    exclude(rows.source_version.isna(), 'source_version_missing')
    for name in ['voting_date', 'forecast_at', 'result_available_at']:
        rows[name] = pd.to_datetime(rows[name], errors='coerce', utc=True)
    exclude(rows.voting_date.isna(), 'voting_date_missing')
    exclude(rows.forecast_at.isna() | rows.forecast_evidence.isna()
            | rows.forecast_evidence.astype(str).str.strip().eq(''), 'forecast_evidence_missing')
    exclude(rows.forecast_at.ge(rows.voting_date), 'forecast_not_before_vote')
    if rows.groupby('vote_id').voting_date.nunique().gt(1).any():
        raise ValueError('An object must have one voting date')
    if rows.groupby('vote_id').forecast_at.nunique().gt(1).any():
        raise ValueError('An object must have one forecast instant')
    rows['target_share'] = rows.yes_count / (rows.yes_count + rows.no_count)
    mapping = {pd.Timestamp(date, tz='UTC'): name for name, dates in [('train', config.train_dates),
               ('validation', config.validation_dates), ('test', config.test_dates)] for date in dates}
    rows['partition'] = rows.voting_date.map(mapping)
    exclude(rows.partition.isna(), 'unassigned_date')
    rows = rows.sort_values(['voting_date', 'vote_id', 'municipality_id']).reset_index(drop=True)
    train = rows.loc[rows.partition.eq('train')]
    predictions = []
    unpredictable = 0
    evaluation_partition = 'test' if config.mode == 'final_test' else 'validation'
    for _, target in rows.loc[rows.partition.eq(evaluation_partition)].iterrows():
        available = (rows.result_available_at.notna() & rows.result_available_at.le(target.forecast_at)
                     & rows.result_availability_evidence.notna()
                     & rows.result_availability_evidence.astype(str).str.strip().ne('')
                     & rows.voting_date.lt(target.voting_date))
        training_pool = rows.loc[available & rows.partition.eq('train')]
        if training_pool.empty:
            unpredictable += 1
            continue
        fallback = float(training_pool.target_share.mean())
        history_pool = rows.loc[available & rows.partition.isin(['train', 'validation'])] if config.history_policy == 'rolling' else training_pool
        local = history_pool.loc[history_pool.municipality_id.eq(target.municipality_id)
                                 & history_pool.geography_id.eq(target.geography_id)]
        history = float(local.target_share.mean()) if not local.empty else fallback
        for model, prediction in [('constant', fallback), ('municipal_history', history)]:
            predictions.append({**target.to_dict(), 'model': model, 'prediction': prediction,
                                'fallback': model == 'municipal_history' and local.empty})
    predictions = pd.DataFrame(predictions, columns=list(rows.columns) + ['model','prediction','fallback'])
    if unpredictable:
        exclusions['no_admissible_training_history'] = unpredictable
    metrics, coverage = {}, {'unpredictable_rows': unpredictable,
        'input_rows': len(prepared), 'eligible_rows': len(rows),
        'partitions': {name: {'rows': len(group), 'objects': int(group.vote_id.nunique()),
                              'dates': int(group.voting_date.nunique())}
                       for name, group in rows.groupby('partition')}}
    def score(group):
        errors = (group.prediction - group.target_share).abs() * 100
        weights = pd.to_numeric(group.get('evaluation_weight', pd.Series(np.nan, index=group.index)), errors='coerce')
        valid = np.isfinite(weights) & weights.gt(0)
        return {'mae_pp': float(errors.mean()), 'rows': len(group),
                'electorate_weighted_mae_pp': float(np.average(errors[valid], weights=weights[valid])) if valid.any() else None,
                'weighted_rows': int(valid.sum())}
    by_date, by_object = [], []
    for model, group in predictions.groupby('model'):
        metrics[model] = score(group)
        coverage[model] = {'rows': len(group), 'objects': int(group.vote_id.nunique()),
                           'dates': int(group.voting_date.nunique()),
                           'fallback_rows': int(group.fallback.sum()),
                           'fallback_fraction': float(group.fallback.mean())}
        for date, subgroup in group.groupby('voting_date'):
            by_date.append({'model': model, 'voting_date': date, **score(subgroup)})
        for vote, subgroup in group.groupby('vote_id'):
            by_object.append({'model': model, 'vote_id': vote, **score(subgroup)})
    return {'manifest': {**asdict(config), 'input_rows': len(prepared),
                          'input_sha256': hashlib.sha256(prepared.to_json(orient='split', date_format='iso').encode()).hexdigest(),
                          'source_versions': sorted(rows.source_version.astype(str).unique().tolist()),
                          'versions': {'python': platform.python_version(), 'pandas': pd.__version__, 'numpy': np.__version__},
                          'weight_origin': 'prepared evaluation_weight; retrospective weights are evaluation only',
                          'forecast_cutoffs': {vote: str(group.forecast_at.iloc[0]) for vote, group in rows.groupby('vote_id')}}, 'partitions': rows[KEYS + ['voting_date','partition']],
            'eligible_rows': rows, 'predictions': predictions, 'coverage': coverage,
            'exclusions': exclusions, 'metrics': metrics,
            'by_date': pd.DataFrame(by_date), 'by_object': pd.DataFrame(by_object)}


def write_artifacts(result: dict, output_dir) -> None:
    """Persist the public result without requiring a Parquet engine."""
    import json
    from pathlib import Path
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    summary = {}
    for name, artifact in result.items():
        if isinstance(artifact, pd.DataFrame):
            artifact.to_csv(output / f'{name}.csv', index=False)
        else:
            summary[name] = artifact
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')


def synthetic_example():
    """Small documented example with explicit illustrative (not real) evidence."""
    records = []
    for municipality, vote, date, yes in [('a','old','2020-01-01',20), ('b','old','2020-01-01',60),
                                         ('a','next','2021-01-01',80), ('c','next','2021-01-01',40),
                                         ('a','final','2022-01-01',90)]:
        records.append(dict(municipality_id=municipality, vote_id=vote, voting_date=date,
            yes_count=yes, no_count=100-yes, geography_id='synthetic-g1', source_version='synthetic-v1',
            result_available_at=date, result_availability_evidence='synthetic-publication',
            forecast_at=str(pd.Timestamp(date) - pd.Timedelta(days=10)),
            forecast_evidence='synthetic-brochure-publication', is_special_unit=False,
            is_subsidiary=False, is_provisional=False))
    return pd.DataFrame(records), EvaluationConfig(('2020-01-01',), ('2021-01-01',), ('2022-01-01',))


def main():
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--synthetic', action='store_true')
    parser.add_argument('--input', type=Path, help='Prepared CSV or Parquet; raw cleaned outcomes alone are insufficient')
    parser.add_argument('--config', type=Path, help='JSON EvaluationConfig with date partitions and policies')
    parser.add_argument('--output', type=Path, default=Path('reports/generated/municipal_evaluation'))
    args = parser.parse_args()
    if args.synthetic:
        if args.input or args.config:
            parser.error('--synthetic cannot be combined with --input/--config')
        rows, config = synthetic_example()
    else:
        if args.input is None or args.config is None:
            parser.error('Real evaluation requires --input and --config with publication and geography evidence; use --synthetic for the reproducible example')
        rows = pd.read_parquet(args.input) if args.input.suffix == '.parquet' else pd.read_csv(args.input, dtype={key: str for key in KEYS})
        config = EvaluationConfig(**json.loads(args.config.read_text()))
    try:
        result = evaluate(rows, config)
    except ValueError as error:
        parser.error(str(error))
    write_artifacts(result, args.output)
    print(json.dumps({'mode': config.mode, 'metrics': result['metrics'], 'output': str(args.output)}, indent=2))


if __name__ == '__main__':
    main()

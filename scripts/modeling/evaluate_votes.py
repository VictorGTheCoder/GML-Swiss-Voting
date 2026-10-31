"""Publication-aware municipal evaluation; see docs/project/municipal_evaluation.md."""
from __future__ import annotations

import hashlib
import platform
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn

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
    validation_windows: tuple[tuple[str, ...], ...] | None = None
    history_policy: str = 'frozen'
    mode: str = 'validation'
    seed: int = 0
    choices_frozen: bool = False
    predictor_allowlist: tuple[str, ...] = ('municipal_history', 'history_missing')
    geography_mode: str = 'historically_existing'
    audit_flag_policy: str = 'exclude'
    ridge_alphas: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0)
    selected_ridge_alphas: dict[str, float] | None = None
    hist_gradient_boosting_candidates: tuple[tuple[int, int, float, int], ...] = tuple(
        (leaves, minimum, rate, 100)
        for leaves in (7, 15) for minimum in (50, 200) for rate in (0.05, 0.1))
    selected_hist_gradient_boosting: dict[str, dict] | None = None
    bootstrap_replicates: int = 1000
    evaluation_weight_origin: str = 'not supplied; evaluation-only weights have unspecified provenance'
    refit_train_validation: bool = False


def _apply_geography(rows, config, crosswalk, exclusions):
    """Apply a validated many-to-one mapping before deriving shares."""
    manifest = {'mode': config.geography_mode,
                'input_references': sorted(rows.geography_id.astype(str).unique().tolist()),
                'crosswalk_versions': [], 'crosswalk_evidence': [],
                'policy': 'prepared reference identity; municipality identifiers alone are insufficient'}
    if crosswalk is None:
        already_harmonized = rows.get('harmonization_applied', pd.Series(False, index=rows.index)).eq(True)
        if already_harmonized.any():
            if any(name not in rows for name in ['crosswalk_version', 'crosswalk_evidence']):
                raise ValueError('Prepared harmonization requires crosswalk provenance')
            provenance = rows.loc[already_harmonized, ['crosswalk_version', 'crosswalk_evidence']]
            if provenance.isna().any().any() or provenance.astype(str).apply(lambda c: c.str.strip().eq('')).any().any():
                raise ValueError('Prepared harmonization requires crosswalk provenance')
            manifest['crosswalk_versions'] = sorted(provenance.crosswalk_version.astype(str).unique().tolist())
            manifest['crosswalk_evidence'] = sorted(provenance.crosswalk_evidence.astype(str).unique().tolist())
        manifest['output_references'] = manifest['input_references']
        return rows, manifest
    required = ['source_municipality_id', 'source_geography_id', 'target_municipality_id',
                'target_geography_id', 'mapping_type', 'crosswalk_version', 'crosswalk_evidence',
                'mapping_available_at', 'target_valid_from']
    missing = set(required) - set(crosswalk.columns)
    if missing:
        raise ValueError(f'Missing crosswalk columns: {sorted(missing)}')
    mapping = crosswalk.copy()
    for name in ['source_municipality_id', 'source_geography_id', 'target_municipality_id', 'target_geography_id']:
        if mapping[name].isna().any() or mapping[name].astype(str).str.strip().eq('').any():
            raise ValueError('Crosswalk requires nonempty source and target identifiers/references')
        mapping[name] = mapping[name].astype(str)
    manifest['crosswalk_sha256'] = hashlib.sha256(crosswalk.to_json(orient='split', date_format='iso').encode()).hexdigest()
    manifest['crosswalk_versions'] = sorted(mapping.crosswalk_version.dropna().astype(str).unique().tolist())
    manifest['crosswalk_evidence'] = sorted(mapping.crosswalk_evidence.dropna().astype(str).unique().tolist())
    manifest['policy'] = 'count aggregation with explicit crosswalk; no allocation across splits'
    source_keys = ['source_municipality_id', 'source_geography_id']
    for _, group in mapping.groupby(source_keys):
        if len(group) > 1 and not (group.mapping_type.eq('split').all() and not group.duplicated().any()):
            raise ValueError('Crosswalk source cardinality must be many-to-one; explicit splits are excluded')
    if mapping.source_geography_id.eq(mapping.target_geography_id).any():
        raise ValueError('Crosswalk cannot harmonize within the same reference state')
    for date in ['mapping_available_at', 'target_valid_from', 'target_valid_to']:
        mapping[date] = pd.to_datetime(mapping[date] if date in mapping else pd.Series(pd.NaT, index=mapping.index), errors='coerce', utc=True, format='mixed')
    for _, target_group in mapping.groupby(['target_municipality_id', 'target_geography_id']):
        supported = target_group.loc[target_group.mapping_type.isin(['identity', 'merger'])]
        if len(supported) > 1 and not supported.mapping_type.eq('merger').all():
            raise ValueError('Many-to-one target cardinality requires explicit merger mappings')
        if any(target_group[date].nunique(dropna=False) > 1 for date in ['target_valid_from', 'target_valid_to']):
            raise ValueError('Target lifetime must agree across crosswalk constituents')
    rows = rows.copy()
    transformed = []
    def exclude(reason):
        exclusions[reason] = exclusions.get(reason, 0) + 1
    for _, original in rows.iterrows():
        candidate = mapping.loc[mapping.source_municipality_id.eq(original.municipality_id)
                                & mapping.source_geography_id.eq(original.geography_id)]
        if candidate.empty:
            target_links = mapping.loc[mapping.target_municipality_id.eq(original.municipality_id)
                                       & mapping.target_geography_id.eq(original.geography_id)]
            if not target_links.empty and config.geography_mode == 'historically_existing':
                link = target_links.iloc[0]
                if pd.isna(link.target_valid_from) or original.forecast_at < link.target_valid_from or (pd.notna(link.target_valid_to) and original.forecast_at >= link.target_valid_to):
                    exclude('target_not_existing_at_forecast')
                    continue
            if original.geography_id in set(mapping.source_geography_id):
                exclude('geography_mapping_missing')
            else:
                transformed.append(original.to_dict())
            continue
        if pd.notna(original.get('harmonization_applied')) and bool(original.get('harmonization_applied')):
            raise ValueError('Cannot apply harmonization twice')
        link = candidate.iloc[0]
        if link.mapping_type not in ['identity', 'merger']:
            exclude('unsupported_geography_mapping')
            continue
        if pd.isna(link.crosswalk_version) or pd.isna(link.crosswalk_evidence) or not str(link.crosswalk_evidence).strip() or not str(link.crosswalk_version).strip():
            exclude('geography_evidence_missing')
            continue
        if config.geography_mode == 'historically_existing':
            if pd.isna(link.mapping_available_at) or link.mapping_available_at > original.forecast_at:
                exclude('geography_mapping_unavailable')
                continue
            if pd.isna(link.target_valid_from) or original.forecast_at < link.target_valid_from or (pd.notna(link.target_valid_to) and original.forecast_at >= link.target_valid_to):
                exclude('target_not_existing_at_forecast')
                continue
        transformed.append({**original.to_dict(), 'municipality_id': link.target_municipality_id,
                            'geography_id': link.target_geography_id, 'source_municipalities': original.municipality_id,
                            'harmonization_applied': True, 'crosswalk_version': link.crosswalk_version,
                            'crosswalk_evidence': link.crosswalk_evidence})
    output = pd.DataFrame(transformed, columns=list(dict.fromkeys(list(rows.columns) +
        ['source_municipalities', 'harmonization_applied', 'crosswalk_version', 'crosswalk_evidence'])))
    aggregated = []
    for _, group in output.groupby(KEYS + ['geography_id'], dropna=False):
        if group.harmonization_applied.eq(True).any():
            reference = group.iloc[0]
            links = mapping.loc[mapping.target_municipality_id.eq(reference.municipality_id)
                                & mapping.target_geography_id.eq(reference.geography_id)
                                & mapping.mapping_type.eq('merger')]
            expected = set(links.source_municipality_id)
            actual = set(group.source_municipalities.dropna())
            if expected and actual != expected:
                exclusions['incomplete_geography_merger'] = exclusions.get('incomplete_geography_merger', 0) + len(group)
                continue
        combined = group.iloc[0].to_dict()
        if len(group) > 1:
            if (~group.harmonization_applied.eq(True)).any():
                raise ValueError('Mapped and already-target rows overlap; cardinality is ambiguous')
            if group.crosswalk_version.nunique() != 1:
                raise ValueError('Mixed crosswalk versions in one target group')
            combined['yes_count'] = group.yes_count.sum()
            combined['no_count'] = group.no_count.sum()
            combined['result_available_at'] = group.result_available_at.max()
            if group.result_available_at.isna().any() or group.result_availability_evidence.isna().any() or group.result_availability_evidence.astype(str).str.strip().eq('').any():
                combined['result_available_at'] = pd.NaT
                combined['result_availability_evidence'] = None
            else:
                combined['result_availability_evidence'] = '|'.join(sorted(group.result_availability_evidence.astype(str).unique()))
            combined['source_version'] = '|'.join(sorted(group.source_version.astype(str).unique()))
            combined['source_municipalities'] = '|'.join(sorted(group.source_municipalities.astype(str)))
            if 'evaluation_weight' in group:
                weights = pd.to_numeric(group.evaluation_weight, errors='coerce')
                combined['evaluation_weight'] = weights.sum() if np.isfinite(weights).all() and weights.gt(0).all() else np.nan
        aggregated.append(combined)
    output = pd.DataFrame(aggregated, columns=output.columns)
    manifest['output_references'] = sorted(output.geography_id.astype(str).unique().tolist())
    return output, manifest


def evaluate(prepared: pd.DataFrame, config: EvaluationConfig, *, geography_crosswalk: pd.DataFrame | None = None, feature_blocks: tuple = (), text_records=None, frozen_experiment=None, history_source=None, domain_records=None) -> dict:
    """Run the complete evaluation seam on prepared rows, returning auditable artifacts."""
    if config.mode == 'final_test' and config.choices_frozen and frozen_experiment is None:
        raise ValueError('Final test requires a frozen experiment artifact')
    if (frozen_experiment is not None and config.mode == 'final_test'
            and config.selected_hist_gradient_boosting is None):
        config = replace(config, selected_hist_gradient_boosting=
            frozen_experiment.get('selected_hist_gradient_boosting', {}))
    missing = set(REQUIRED) - set(prepared.columns)
    if missing:
        raise ValueError(f'Missing prepared columns: {sorted(missing)}')
    date_groups = [pd.to_datetime(list(dates), utc=True, format='mixed').normalize() for dates in
                   [config.train_dates, config.validation_dates, config.test_dates]]
    all_dates = [date for group in date_groups for date in group]
    if len(all_dates) != len(set(all_dates)):
        raise ValueError('Partition dates must be disjoint and unique')
    if any(len(group) == 0 for group in date_groups):
        raise ValueError('All three date partitions must be declared')
    if not (max(date_groups[0]) < min(date_groups[1]) and max(date_groups[1]) < min(date_groups[2])):
        raise ValueError('Partitions must be chronological')
    window_groups = ([pd.to_datetime(list(group), utc=True, format='mixed').normalize() for group in config.validation_windows]
                     if config.validation_windows is not None else [date_groups[1]])
    window_dates = [date for group in window_groups for date in group]
    if (any(len(group) == 0 for group in window_groups)
            or len(window_dates) != len(set(window_dates))
            or set(window_dates) != set(date_groups[1])
            or any(window_groups[i].max() >= window_groups[i+1].min()
                   for i in range(len(window_groups)-1))):
        raise ValueError('validation window dates must cover each validation date exactly once in chronological order')
    if config.history_policy not in ['frozen', 'rolling']:
        raise ValueError('Invalid history_policy')
    if config.mode not in ['validation', 'final_test']:
        raise ValueError('Invalid evaluation mode')
    if config.mode == 'final_test' and not config.choices_frozen:
        raise ValueError('Final test requires frozen choices')
    if config.mode == 'validation' and config.selected_hist_gradient_boosting is not None:
        raise ValueError('selected_hist_gradient_boosting may only be loaded in final_test mode')
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
    rows['geography_id'] = rows.geography_id.astype(str)
    exclude(rows.source_version.isna() | rows.source_version.astype(str).str.strip().eq(''), 'source_version_missing')
    for name in ['voting_date', 'forecast_at', 'result_available_at']:
        rows[name] = pd.to_datetime(rows[name], errors='coerce', utc=True, format='mixed')
    rows['voting_date'] = rows.voting_date.dt.normalize()
    exclude(rows.voting_date.isna(), 'voting_date_missing')
    exclude(rows.forecast_at.isna() | rows.forecast_evidence.isna()
            | rows.forecast_evidence.astype(str).str.strip().eq(''), 'forecast_evidence_missing')
    exclude(rows.forecast_at.ge(rows.voting_date), 'forecast_not_before_vote')
    if rows.groupby('vote_id').voting_date.nunique().gt(1).any():
        raise ValueError('An object must have one voting date')
    if rows.groupby('vote_id').forecast_at.nunique().gt(1).any():
        raise ValueError('An object must have one forecast instant')
    rows, geography = _apply_geography(rows, config, geography_crosswalk, exclusions)
    rows['target_share'] = rows.yes_count / (rows.yes_count + rows.no_count)
    mapping = {date: name for name, dates in zip(['train','validation','test'],date_groups) for date in dates}
    rows['partition'] = rows.voting_date.map(mapping)
    history_pool = rows.copy()
    if history_source is not None:
        history_pool = history_source.copy()
        for name in ['voting_date', 'forecast_at', 'result_available_at']:
            history_pool[name] = pd.to_datetime(history_pool[name], errors='coerce', utc=True, format='mixed')
        for name in KEYS + ['geography_id']:
            history_pool[name] = history_pool[name].astype('string')
        for name in ('yes_count','no_count'):
            history_pool[name] = pd.to_numeric(history_pool[name], errors='coerce')
        for flag in FLAGS:
            history_pool = history_pool.loc[history_pool[flag].eq(False)]
        for flag in [c for c in history_pool if c.startswith('flag_')]:
            history_pool = history_pool.loc[history_pool[flag].eq(False)]
        if 'preparation_status' in history_pool:
            history_pool = history_pool.loc[history_pool.preparation_status.eq('ready_for_enrichment')]
        history_pool, _ = _apply_geography(history_pool, config, geography_crosswalk, {})
        from scripts.modeling.voting_history import validated_vote_shares
        history_pool['target_share'] = validated_vote_shares(history_pool)
    exclude(rows.partition.isna(), 'unassigned_date')
    rows = rows.sort_values(['voting_date', 'vote_id', 'municipality_id']).reset_index(drop=True)
    # Pin every label available for fitting/model selection, excluding reserved test labels.
    pretest_labels = rows.loc[rows.partition.isin(['train', 'validation']),
                              KEYS + ['voting_date', 'partition', 'yes_count', 'no_count']]
    pretest_labels_sha256 = hashlib.sha256(
        pretest_labels.to_json(orient='split', date_format='iso').encode()).hexdigest()
    from scripts.modeling.feature_blocks import join_feature_blocks
    from scripts.modeling.regularized_votes import regularized_predictions
    from scripts.modeling.voting_history import build_historical_features
    history = build_historical_features(rows,config)
    from scripts.modeling.voting_history import HISTORY_FEATURES, build_v1_history_features
    v1_history = build_v1_history_features(rows, history_pool, config, domain_records)
    joined, join_report, block_manifest, block_coverage = join_feature_blocks(rows, feature_blocks, config.geography_mode)
    baseline_design = history[['municipal_history','history_missing']]
    if history_source is not None:
        baseline_design = baseline_design.rename(columns={'history_missing':'baseline_history_missing'})
        design = pd.concat([baseline_design, v1_history[list(HISTORY_FEATURES)], joined], axis=1)
    else:
        design = pd.concat([baseline_design, joined], axis=1)
    from scripts.modeling.final_evaluation import _digest, verify_frozen_experiment
    history_availability_columns = [name for name in REQUIRED + [
        'preparation_status', 'result_availability_status', 'result_source', 'result_source_version',
        'forecast_source', 'forecast_source_version', 'crosswalk_version', 'crosswalk_evidence',
    ] if name in history_pool and name not in ('yes_count','no_count')]
    run_manifest = {**asdict(config), 'input_rows': len(prepared),
                          'input_sha256': hashlib.sha256(prepared.to_json(orient='split', date_format='iso').encode()).hexdigest(),
                          'computed_history_signature': {'source_availability_sha256': hashlib.sha256(history_pool[history_availability_columns].to_json(orient='split',date_format='iso').encode()).hexdigest(), 'pretest_context_labels_sha256': hashlib.sha256(history_pool.loc[history_pool.voting_date.lt(min(date_groups[2])), KEYS + ['yes_count','no_count']].to_json(orient='split').encode()).hexdigest(), 'domains_sha256': _digest(domain_records.to_json(orient='split',date_format='iso')) if domain_records is not None else None},
                          'computed_history': {'version': 'v1', 'history_policy': config.history_policy, 'features': list(HISTORY_FEATURES), 'source_sha256': hashlib.sha256(history_pool.to_json(orient='split',date_format='iso').encode()).hexdigest(), 'domains_sha256': hashlib.sha256(domain_records.to_json(orient='split',date_format='iso').encode()).hexdigest() if domain_records is not None else None},
                          'geography': geography, 'feature_blocks': block_manifest, 'regularized': {},
                          'source_versions': sorted(rows.source_version.astype(str).unique().tolist()),
                          'implementation_sha256': {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest() for name in ['evaluate_votes.py','regularized_votes.py','boosting_votes.py','expanding_windows.py','feature_blocks.py','text_votes.py','final_evaluation.py','voting_history.py','vote_metrics.py','../federal_explanations/federal_explanations_temporal.py']},
                          'versions': {'python': platform.python_version(), 'pandas': pd.__version__, 'numpy': np.__version__, 'scikit-learn': sklearn.__version__},
                          'weight_origin': config.evaluation_weight_origin,
                          'experiment_configuration': asdict(config),
                          'prepared_availability_sha256': hashlib.sha256(rows[KEYS + ['voting_date','source_version','geography_id','forecast_at','forecast_evidence','result_available_at','result_availability_evidence']].to_json(orient='split',date_format='iso').encode()).hexdigest(),
                          'partition_keys_sha256': hashlib.sha256(rows[KEYS+['voting_date','partition']].to_json(orient='split',date_format='iso').encode()).hexdigest(),
                          'pretest_labels_sha256': pretest_labels_sha256,
                          'text_records_sha256': _digest(text_records),
                          'text_records_requested': text_records is not None,
                          'forecast_cutoffs': {vote: str(group.forecast_at.iloc[0]) for vote, group in rows.groupby('vote_id')}}
    if frozen_experiment is not None:
        if config.mode != 'final_test':
            raise ValueError('A frozen experiment artifact is loaded only in final_test mode')
        verify_frozen_experiment(run_manifest,frozen_experiment)
        run_manifest['frozen_experiment_sha256'] = frozen_experiment['sha256']
    evaluation_partition = 'test' if config.mode == 'final_test' else 'validation'
    evaluation = rows.partition.eq(evaluation_partition)
    predictable = history.training_mean.notna()
    unpredictable = int((evaluation & ~predictable).sum())
    targets = rows.loc[evaluation & predictable]
    predictions = targets.loc[targets.index.repeat(2)].reset_index(drop=True)
    predictions['model'] = np.tile(['constant','municipal_history'],len(targets))
    predictions['prediction'] = np.column_stack([history.loc[targets.index,'training_mean'],history.loc[targets.index,'municipal_history']]).ravel()
    predictions['raw_prediction'] = predictions['prediction']
    predictions['clipped'] = False
    predictions['fallback'] = np.column_stack([np.zeros(len(targets),dtype=bool),history.loc[targets.index,'history_missing'].astype(bool)]).ravel()
    regularized_manifest = {}
    admissible_blocks = ()
    fitting_partitions = ['train','validation'] if config.mode == 'final_test' and config.refit_train_validation else ['train']
    active_history_rows = rows.partition.isin(fitting_partitions) | rows.index.isin(targets.index)
    unresolved_history = {}
    for prefix in ('history','history_5y','history_same_domain'):
        statuses = v1_history.loc[active_history_rows, prefix+'_status']
        unknown = statuses.loc[~statuses.isin(['known','no_antecedents'])]
        if not unknown.empty:
            unresolved_history[prefix] = {str(status): int(count) for status,count in unknown.value_counts(dropna=False).items()}
    history_frozen_skipped = frozen_experiment is not None and 'ridge_v1_history' not in frozen_experiment['nontext_choices']
    computed_history_enabled = history_source is not None and not unresolved_history and not history_frozen_skipped
    run_manifest['computed_history'].update(
        status='not_requested' if history_source is None else 'enabled' if computed_history_enabled else 'skipped',
        reason=('skipped_in_frozen_validation' if history_source is not None and history_frozen_skipped
                else 'unresolved_history_availability' if history_source is not None and unresolved_history else None),
        unresolved_status_counts=unresolved_history,
        active_rows=int(active_history_rows.sum()),
    )
    if feature_blocks or history_source is not None:
        admissible_blocks = tuple(block for block in feature_blocks
                                  if block.prerequisite_reason is None
                                  and block_coverage[block.block_id]['matched_rows'] > 0)
        regularized, regularized_manifest = regularized_predictions(rows, config, predictions, design, admissible_blocks, computed_history=computed_history_enabled)
        if history_source is not None and not computed_history_enabled:
            regularized_manifest['ridge_v1_history'] = {
                'status': 'skipped', 'reason': run_manifest['computed_history']['reason']}
        predictions = pd.concat([predictions, regularized], ignore_index=True)
    hist_gradient_boosting_manifest = {}
    if feature_blocks:
        from scripts.modeling.boosting_votes import hist_gradient_boosting_predictions
        boosted, hist_gradient_boosting_manifest = hist_gradient_boosting_predictions(
            rows, config, predictions, design,
            admissible_blocks)
        predictions = pd.concat([predictions, boosted], ignore_index=True)
    if unpredictable:
        exclusions['no_admissible_training_history'] = unpredictable
    metrics, coverage = {}, {'unpredictable_rows': unpredictable,
        'input_rows': len(prepared), 'eligible_rows': len(rows), 'feature_blocks': block_coverage,
        'partitions': {name: {'rows': len(group), 'objects': int(group.vote_id.nunique()),
                              'dates': int(group.voting_date.nunique())}
                       for name, group in rows.groupby('partition')}}
    from scripts.modeling.vote_metrics import score_predictions as score
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
    text_result = {}
    if text_records is not None:
        from scripts.modeling.text_votes import text_experiment
        text_frozen_skipped = frozen_experiment is not None and frozen_experiment['text_choices']['status'] != 'evaluated'
        text_result = text_experiment(rows, config, predictions, design, admissible_blocks, [] if text_frozen_skipped else text_records)
        if text_frozen_skipped:
            text_result['reason'] = 'Text branch was skipped in frozen validation; final nontext evaluation proceeds'
            text_result['frozen_validation_status'] = frozen_experiment['text_choices']['status']
    from scripts.modeling.feature_ablations import ablation_reports
    ablations = ablation_reports(predictions, feature_blocks, block_manifest, block_coverage, regularized_manifest, config.mode)
    run_manifest['regularized'] = regularized_manifest
    run_manifest['hist_gradient_boosting'] = hist_gradient_boosting_manifest
    result = {'text_experiment': text_result, 'ablations': ablations, 'manifest': run_manifest, 'partitions': rows[KEYS + ['voting_date','partition']],
            'eligible_rows': rows, 'predictions': predictions, 'coverage': coverage,
            'exclusions': exclusions, 'metrics': metrics,
            'by_date': pd.DataFrame(by_date), 'by_object': pd.DataFrame(by_object),
            'history_report': pd.concat([rows[KEYS], v1_history],axis=1),
            'joined_features': pd.concat([rows[KEYS], design],axis=1), 'join_report': join_report}
    from scripts.modeling.final_evaluation import (
        paired_uncertainty,
        verify_frozen_experiment,
    )
    combined_predictions = predictions
    if text_result.get('status') == 'evaluated':
        combined_predictions = pd.concat([predictions,text_result['predictions']],ignore_index=True)
    summaries = [{'model':name,'population':'wider_nontext',**score,**coverage.get(name,{})}
                 for name,score in metrics.items()]
    summaries.extend({'model':name,'population':'paired_text_eligible',**score}
                     for name,score in text_result.get('metrics',{}).items())
    if text_result.get('status') == 'skipped':
        summaries.append({'model':'paired_text','population':'paired_text_eligible','status':'skipped','reason':text_result['reason']})
    result['model_summary'] = pd.DataFrame(summaries)
    result['paired_uncertainty'] = paired_uncertainty(combined_predictions,seed=config.seed,replicates=config.bootstrap_replicates)
    return result


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
            if name == 'text_experiment' and artifact:
                artifact = dict(artifact)
                artifact.pop('predictions').to_csv(output / 'text_predictions.csv', index=False)
            summary[name] = artifact
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')


def synthetic_example():
    """Small documented example with explicit illustrative (not real) evidence."""
    records = []
    for municipality, vote, date, yes in [('a','old','2020-01-01',20), ('b','old','2020-01-01',60),
                                         ('a','next','2021-01-01',80), ('c','next','2021-01-01',40),
                                         ('a','final','2022-01-01',90)]:
        records.append({'municipality_id': municipality, 'vote_id': vote, 'voting_date': date,
            'yes_count': yes, 'no_count': 100-yes, 'geography_id': 'synthetic-g1', 'source_version': 'synthetic-v1',
            'result_available_at': date, 'result_availability_evidence': 'synthetic-publication',
            'forecast_at': str(pd.Timestamp(date) - pd.Timedelta(days=10)),
            'forecast_evidence': 'synthetic-brochure-publication', 'is_special_unit': False,
            'is_subsidiary': False, 'is_provisional': False})
    return pd.DataFrame(records), EvaluationConfig(('2020-01-01',), ('2021-01-01',), ('2022-01-01',))


def main():
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--synthetic', action='store_true')
    parser.add_argument('--synthetic-text', action='store_true', help='Include illustrative validated text records with --synthetic')
    parser.add_argument('--freeze-output', type=Path, help='Write integrity-checked frozen choices after validation')
    parser.add_argument('--final-test', action='store_true', help='Explicit final-test mode; requires frozen experiment')
    parser.add_argument('--frozen-experiment', type=Path, help='Previously saved validation freeze artifact')
    parser.add_argument('--synthetic-features', action='store_true', help='Include an illustrative prepared STATPOP block with --synthetic')
    parser.add_argument('--input', type=Path, help='Prepared CSV or Parquet; raw cleaned outcomes alone are insufficient')
    parser.add_argument('--history-source', type=Path, help='Complete V1 prepared Parquet, including pre-training history context')
    parser.add_argument('--domain-records', type=Path, help='V1 domain_records.parquet with version-bound eligibility')
    parser.add_argument('--blocks', type=Path, help='JSON descriptors of prepared feature blocks')
    parser.add_argument('--text-records', type=Path, help='JSON list of reviewed version-bound brochure records; eligibility is rechecked')
    parser.add_argument('--crosswalk', type=Path, help='Optional prepared geography crosswalk CSV')
    parser.add_argument('--config', type=Path, help='JSON EvaluationConfig with date partitions and policies')
    parser.add_argument('--output', type=Path, default=Path('reports/generated/municipal_evaluation'))
    args = parser.parse_args()
    if args.domain_records and not args.history_source:
        parser.error('--domain-records requires --history-source')
    if args.synthetic_text and not args.synthetic:
        parser.error('--synthetic-text requires --synthetic')
    if args.final_test != bool(args.frozen_experiment):
        parser.error('--final-test and --frozen-experiment must be supplied together')
    if args.final_test and args.freeze_output:
        parser.error('--freeze-output is only for validation')
    frozen = json.loads(args.frozen_experiment.read_text()) if args.frozen_experiment else None
    if args.synthetic_features and not args.synthetic:
        parser.error('--synthetic-features requires --synthetic')
    if args.synthetic:
        if args.input or args.config or args.crosswalk or args.blocks or args.history_source or args.domain_records:
            parser.error('--synthetic cannot be combined with --input/--config')
        rows, config = synthetic_example()
    else:
        if args.input is None or (args.config is None and frozen is None):
            parser.error('Real evaluation requires --input and --config with publication and geography evidence; use --synthetic for the reproducible example')
        rows = pd.read_parquet(args.input) if args.input.suffix == '.parquet' else pd.read_csv(args.input, dtype=dict.fromkeys(KEYS + ['geography_id'], str))
        config = EvaluationConfig(**(json.loads(args.config.read_text()) if args.config else frozen['signature']['configuration']))
    if args.final_test:
        from dataclasses import replace
        if args.synthetic:
            config = EvaluationConfig(**frozen['signature']['configuration'])
        config = replace(config,mode='final_test',choices_frozen=True,
            selected_ridge_alphas=frozen['selected_ridge_alphas'],
            selected_hist_gradient_boosting=frozen.get('selected_hist_gradient_boosting', {}))
    elif config.mode == 'final_test':
        parser.error('Final config requires explicit --final-test and --frozen-experiment')
    try:
        from scripts.modeling.feature_blocks import (
            load_feature_blocks,
            synthetic_feature_example,
        )
        blocks = (synthetic_feature_example(),) if args.synthetic_features else load_feature_blocks(args.blocks) if args.blocks else ()
        from scripts.modeling.text_votes import synthetic_text_example
        records = synthetic_text_example(rows) if args.synthetic_text else json.loads(args.text_records.read_text()) if args.text_records else None
        result = evaluate(rows, config,
            history_source=pd.read_parquet(args.history_source) if args.history_source else None,
            domain_records=pd.read_parquet(args.domain_records) if args.domain_records else None,
            frozen_experiment=frozen, text_records=records, feature_blocks=blocks, geography_crosswalk=pd.read_csv(args.crosswalk, dtype=str) if args.crosswalk else None)
    except ValueError as error:
        parser.error(str(error))
    if args.freeze_output:
        from scripts.modeling.final_evaluation import freeze_experiment
        args.freeze_output.parent.mkdir(parents=True,exist_ok=True)
        args.freeze_output.write_text(json.dumps(freeze_experiment(result),indent=2,allow_nan=False)+'\n')
    write_artifacts(result, args.output)
    print(json.dumps({'mode': config.mode, 'metrics': result['metrics'], 'output': str(args.output)}, indent=2))


if __name__ == '__main__':
    main()

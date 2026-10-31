"""Dense, allowlist-driven histogram gradient boosting comparison."""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import MissingIndicator, SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from scripts.modeling.expanding_windows import select_training_rows, window_dates

SETTING_NAMES = ('max_leaf_nodes', 'min_samples_leaf', 'learning_rate', 'max_iter')


def _pipeline(numeric, categorical, settings, seed):
    transforms = []
    if numeric:
        transforms.append(('numeric', SimpleImputer(strategy='median', keep_empty_features=True), numeric))
    transforms.append(('missingness', MissingIndicator(features='all', error_on_new=False), numeric + categorical))
    if categorical:
        transforms.append(('categorical', Pipeline([
            ('impute', SimpleImputer(strategy='constant', fill_value='missing', keep_empty_features=True)),
            ('encode', OneHotEncoder(handle_unknown='ignore', sparse_output=False)),
        ]), categorical))
    estimator = HistGradientBoostingRegressor(
        max_leaf_nodes=settings[0], min_samples_leaf=settings[1],
        learning_rate=settings[2], max_iter=settings[3], early_stopping=False,
        random_state=seed)
    return Pipeline([('prepare', ColumnTransformer(transforms, sparse_threshold=0.0)), ('model', estimator)])


def _feature_sets(blocks, baseline_missing='history_missing'):
    feature_sets = {'hist_gradient_boosting_history': (['municipal_history', baseline_missing], [])}
    for block in blocks:
        feature_sets[f'hist_gradient_boosting_{block.block_id}'] = (
            ['municipal_history', baseline_missing] + [f'{block.block_id}__{name}' for name in block.numeric_features],
            [f'{block.block_id}__{name}' for name in block.categorical_features])
    if len(blocks) > 1:
        feature_sets['hist_gradient_boosting_combined'] = (
            ['municipal_history', baseline_missing] + [
                f'{block.block_id}__{name}' for block in blocks for name in block.numeric_features],
            [f'{block.block_id}__{name}' for block in blocks for name in block.categorical_features])
    return feature_sets


def _settings_tuple(setting):
    if isinstance(setting, dict):
        if set(setting) != set(SETTING_NAMES):
            raise ValueError('selected_hist_gradient_boosting settings must declare all four estimator parameters')
        return tuple(setting[name] for name in SETTING_NAMES)
    return tuple(setting)


def hist_gradient_boosting_predictions(rows, config, baseline, design, blocks):
    """Fit a deterministic dense comparator once at each chronological window boundary."""
    try:
        candidates = tuple(_settings_tuple(setting) for setting in config.hist_gradient_boosting_candidates)
    except (TypeError, ValueError):
        raise ValueError('hist_gradient_boosting_candidates must contain four-value settings') from None
    def valid(setting):
        return (
            len(setting) == 4
            and isinstance(setting[0], (int, np.integer)) and not isinstance(setting[0], bool) and setting[0] >= 2
            and isinstance(setting[1], (int, np.integer)) and not isinstance(setting[1], bool) and setting[1] >= 1
            and isinstance(setting[2], (int, float, np.number)) and not isinstance(setting[2], bool)
            and np.isfinite(setting[2]) and setting[2] > 0
            and isinstance(setting[3], (int, np.integer)) and not isinstance(setting[3], bool) and setting[3] >= 1)
    if (not candidates or len(set(candidates)) != len(candidates) or any(not valid(setting) for setting in candidates)):
        raise ValueError('hist_gradient_boosting_candidates must contain unique valid (max_leaf_nodes, min_samples_leaf, learning_rate, max_iter) settings')
    partition = 'test' if config.mode == 'final_test' else 'validation'
    keys = set(zip(baseline.municipality_id, baseline.vote_id))
    evaluation_rows = rows.loc[rows.partition.eq(partition) & pd.Series(
        [(municipality, vote) in keys for municipality, vote in zip(rows.municipality_id, rows.vote_id)],
        index=rows.index)]
    feature_sets = _feature_sets(blocks, 'baseline_history_missing' if 'baseline_history_missing' in design else 'history_missing')
    frozen_settings = config.selected_hist_gradient_boosting or {}
    if evaluation_rows.empty:
        return pd.DataFrame(columns=baseline.columns), {}

    declared_windows = window_dates(config, partition)
    output, manifest = [], {}
    for name, (numeric, categorical) in feature_sets.items():
        if config.mode == 'final_test' and name not in frozen_settings:
            manifest[name] = {'status': 'skipped', 'reason': 'No frozen histogram gradient boosting settings supplied'}
            continue
        if frozen_settings.get(name) is not None:
            frozen = _settings_tuple(frozen_settings[name])
            if frozen not in candidates:
                raise ValueError(f'Selected settings for {name} must be in hist_gradient_boosting_candidates')
            model_candidates = (frozen,)
        else:
            model_candidates = candidates
        matrix = design[numeric + categorical].copy()
        candidate_predictions = {settings: [] for settings in model_candidates}
        windows_manifest = []
        for index, dates in enumerate(declared_windows):
            window_eval = evaluation_rows.loc[evaluation_rows.voting_date.isin(dates)]
            if window_eval.empty:
                windows_manifest.append({'window': index + 1, 'validation_dates': dates.strftime('%Y-%m-%d').tolist(),
                    'status': 'no_eligible_evaluation_rows', 'training_dates': [],
                    'training_row_keys': [], 'validation_row_keys': []})
                continue
            first_forecast = window_eval.forecast_at.min()
            train = select_training_rows(rows, config, partition, declared_windows,
                index, first_forecast)
            common = {'window': index + 1,
                'validation_dates': sorted(window_eval.voting_date.dt.strftime('%Y-%m-%d').unique().tolist()),
                'validation_row_keys': list(map(list, zip(window_eval.municipality_id, window_eval.vote_id)))}
            if train.empty:
                windows_manifest.append({**common, 'status': 'no_published_training_targets',
                    'first_forecast_at': str(first_forecast), 'fit_cutoff': None,
                    'training_dates': [], 'training_row_keys': []})
                continue
            fit_cutoff = train.result_available_at.max()
            if fit_cutoff > first_forecast:
                raise ValueError('Training target availability exceeds the first forecast instant of its window')
            for settings in model_candidates:
                fit = _pipeline(numeric, categorical, settings, config.seed)
                fit.fit(matrix.loc[train.index], train.target_share)
                raw = fit.predict(matrix.loc[window_eval.index])
                clipped = np.clip(raw, 0, 1)
                frame = window_eval.copy()
                frame['model'] = name
                frame['raw_prediction'] = raw.astype(float)
                frame['prediction'] = clipped.astype(float)
                frame['clipped'] = ~np.isclose(raw, clipped)
                frame['fallback'] = False
                frame['validation_window'] = index + 1
                candidate_predictions[settings].append(frame)
            windows_manifest.append({**common, 'status': 'evaluated',
                'training_dates': sorted(train.voting_date.dt.strftime('%Y-%m-%d').unique().tolist()),
                'first_forecast_at': str(first_forecast), 'fit_cutoff': str(fit_cutoff),
                'training_partitions': sorted(train.partition.unique().tolist()), 'training_rows': len(train),
                'training_row_keys': list(map(list, zip(train.municipality_id, train.vote_id))),
                'training_design_sha256': hashlib.sha256(matrix.loc[train.index].to_json(orient='split').encode()).hexdigest(),
                'refit_schedule': 'fit estimator and preprocessing once at window start; fixed for every row in this window'})
        scores = {}
        for settings, frames in candidate_predictions.items():
            joined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
            scores[settings] = float(np.mean(np.abs(joined.prediction - joined.target_share)) * 100) if len(joined) else None
        available_scores = {settings: score for settings, score in scores.items() if score is not None}
        if not available_scores:
            manifest[name] = {'status': 'no_evaluable_windows', 'settings': None,
                'validation_scores_pp': {str(settings): score for settings, score in scores.items()},
                'windows': windows_manifest}
            continue
        selected = next(iter(model_candidates)) if frozen_settings.get(name) is not None else min(
            available_scores, key=lambda settings: (available_scores[settings], settings))
        chosen = pd.concat(candidate_predictions[selected], ignore_index=True)
        output.extend(chosen.to_dict('records'))
        fitted_dates = sorted({date for window in windows_manifest for date in window.get('training_dates', [])})
        manifest[name] = {'status': 'evaluated',
            'settings': dict(zip(SETTING_NAMES, selected)),
            'candidate_settings': [dict(zip(SETTING_NAMES, setting)) for setting in model_candidates],
            'validation_scores_pp': {str(settings): score for settings, score in scores.items()} if frozen_settings.get(name) is None else {},
            'training_dates': fitted_dates,
            'validation_dates': sorted(evaluation_rows.voting_date.dt.strftime('%Y-%m-%d').unique().tolist()) if frozen_settings.get(name) is None else [],
            'preprocessing': 'training-only median numeric imputation; training-only categorical imputation and dense one-hot encoding; allowlisted features and missingness indicators',
            'early_stopping': False, 'random_state': config.seed,
            'sklearn_version': sklearn.__version__, 'features': numeric + categorical,
            'training_design_sha256': hashlib.sha256('|'.join(window.get('training_design_sha256', '') for window in windows_manifest).encode()).hexdigest(),
            'selection': 'frozen settings; no evaluation targets used in fitting/selection' if frozen_settings.get(name) is not None else 'aggregate chronological expanding-window validation; scores used for selection',
            'refit_schedule': 'one estimator and preprocessing fit at each validation-window boundary; no within-window refit',
            'windows': windows_manifest}
    return pd.DataFrame(output), manifest

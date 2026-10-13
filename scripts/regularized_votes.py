"""Chronological regularized references over admissible prepared features."""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
import sklearn
from scripts.expanding_windows import select_training_rows, window_dates
from sklearn.compose import ColumnTransformer
from sklearn.impute import MissingIndicator, SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def historical_features(rows, config):
    from scripts.voting_history import build_historical_features
    return build_historical_features(rows,config)[['municipal_history','history_missing']]


def _pipeline(numeric, categorical, alpha):
    transforms = [('numeric', Pipeline([('impute', SimpleImputer(strategy='median', keep_empty_features=True)),
                                       ('scale',StandardScaler())]), numeric)]
    transforms.append(('missingness', MissingIndicator(features='all',error_on_new=False), numeric+categorical))
    if categorical:
        transforms.append(('categorical', Pipeline([('impute',SimpleImputer(strategy='constant',fill_value='missing',keep_empty_features=True)),
                                                    ('encode',OneHotEncoder(handle_unknown='ignore',sparse_output=False))]), categorical))
    return Pipeline([('prepare',ColumnTransformer(transforms)), ('ridge',Ridge(alpha=alpha))])


def regularized_predictions(rows, config, baseline, design, blocks):
    """Fit Ridge once per declared validation window and keep each fit fixed within it."""
    partition = 'test' if config.mode == 'final_test' else 'validation'
    keys = set(zip(baseline.municipality_id,baseline.vote_id))
    evaluation_rows = rows.loc[rows.partition.eq(partition) & pd.Series(
        [(m,v) in keys for m,v in zip(rows.municipality_id,rows.vote_id)],index=rows.index)]
    expected_models = ['ridge_history'] + [f'ridge_{block.block_id}' for block in blocks]
    if config.mode == 'final_test' and (not config.selected_ridge_alphas or any(name not in config.selected_ridge_alphas for name in expected_models)):
        raise ValueError('Final test requires selected_ridge_alphas for every regularized model')
    if not config.ridge_alphas or any(not np.isfinite(alpha) or alpha <= 0 for alpha in config.ridge_alphas):
        raise ValueError('ridge_alphas must be finite positive candidates')
    if evaluation_rows.empty:
        return pd.DataFrame(columns=baseline.columns), {}

    feature_sets = {'ridge_history': (['municipal_history','history_missing'],[])}
    for block in blocks:
        feature_sets[f'ridge_{block.block_id}'] = (
            ['municipal_history','history_missing'] + [f'{block.block_id}__{name}' for name in block.numeric_features],
            [f'{block.block_id}__{name}' for name in block.categorical_features])
    if len(blocks) > 1:
        feature_sets['ridge_combined'] = (
            ['municipal_history','history_missing'] + [f'{block.block_id}__{name}'
                for block in blocks for name in block.numeric_features],
            [f'{block.block_id}__{name}' for block in blocks for name in block.categorical_features])

    declared_windows = window_dates(config, partition)
    output, manifest = [], {}
    for name, (numeric,categorical) in feature_sets.items():
        frozen_alpha = config.selected_ridge_alphas.get(name) if config.selected_ridge_alphas else None
        if frozen_alpha is not None and (not np.isfinite(frozen_alpha) or frozen_alpha <= 0):
            raise ValueError('selected_ridge_alphas must be finite positive values')
        candidates = (frozen_alpha,) if frozen_alpha is not None else config.ridge_alphas
        matrix = design[numeric+categorical].copy()
        for column in categorical:
            matrix[column] = matrix[column].where(matrix[column].notna(),np.nan)
        candidate_predictions = {alpha: [] for alpha in candidates}
        window_manifest = []

        for index, dates in enumerate(declared_windows):
            window_eval = evaluation_rows.loc[evaluation_rows.voting_date.isin(dates)]
            if window_eval.empty:
                window_manifest.append({'window': index + 1,
                    'validation_dates': dates.strftime('%Y-%m-%d').tolist(),
                    'status': 'no_eligible_evaluation_rows', 'training_dates': [],
                    'training_row_keys': [], 'validation_row_keys': []})
                continue
            first_forecast = window_eval.forecast_at.min()
            train = select_training_rows(rows, config, partition, declared_windows,
                index, first_forecast)
            if train.empty:
                window_manifest.append({'window': index + 1,
                    'validation_dates': sorted(window_eval.voting_date.dt.strftime('%Y-%m-%d').unique().tolist()),
                    'status': 'no_published_training_targets', 'first_forecast_at': str(first_forecast),
                    'fit_cutoff': None, 'training_dates': [], 'training_row_keys': [],
                    'validation_row_keys': list(map(list, zip(window_eval.municipality_id,window_eval.vote_id)))})
                continue
            fit_cutoff = train.result_available_at.max()
            if fit_cutoff > first_forecast:
                raise ValueError('Training target availability exceeds the first forecast instant of its window')
            for alpha in candidates:
                fit = _pipeline(numeric,categorical,alpha)
                fit.fit(matrix.loc[train.index],train.target_share)
                raw = fit.predict(matrix.loc[window_eval.index])
                clipped = np.clip(raw,0,1)
                frame = window_eval.copy()
                frame['model'] = name
                frame['raw_prediction'] = raw.astype(float)
                frame['prediction'] = clipped.astype(float)
                frame['clipped'] = ~np.isclose(raw,clipped)
                frame['fallback'] = False
                frame['validation_window'] = index + 1
                candidate_predictions[alpha].append(frame)
            window_manifest.append({'window': index + 1,
                'status': 'evaluated', 'validation_dates': sorted(window_eval.voting_date.dt.strftime('%Y-%m-%d').unique().tolist()),
                'training_dates': sorted(train.voting_date.dt.strftime('%Y-%m-%d').unique().tolist()),
                'first_forecast_at': str(first_forecast), 'fit_cutoff': str(fit_cutoff),
                'training_partitions': sorted(train.partition.unique().tolist()),
                'training_rows': len(train),
                'training_row_keys': list(map(list, zip(train.municipality_id,train.vote_id))),
                'training_design_sha256': hashlib.sha256(matrix.loc[train.index].to_json(orient='split').encode()).hexdigest(),
                'validation_row_keys': list(map(list, zip(window_eval.municipality_id,window_eval.vote_id))),
                'refit_schedule': 'fit estimator and preprocessing once at window start; fixed for every row in this window'})

        scores = {}
        for alpha, frames in candidate_predictions.items():
            joined = pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
            scores[alpha] = float(np.mean(np.abs(joined.prediction-joined.target_share))*100) if len(joined) else None
        available_scores = {alpha:score for alpha,score in scores.items() if score is not None}
        if not available_scores:
            manifest[name] = {'selected_alpha': frozen_alpha,
                'validation_scores_pp': {str(k):v for k,v in scores.items()},
                'windows': window_manifest, 'status': 'no_evaluable_windows'}
            continue
        selected = frozen_alpha if frozen_alpha is not None else min(available_scores,key=lambda alpha:(available_scores[alpha],alpha))
        if selected not in available_scores:
            raise ValueError('Selected Ridge alpha has no eligible window scores')
        chosen = pd.concat(candidate_predictions[selected],ignore_index=True)
        output.extend(chosen.to_dict('records'))
        fitted_dates = sorted({date for window in window_manifest
            for date in window.get('training_dates', [])})
        manifest[name] = {'selected_alpha': selected,
            'candidate_alphas': list(candidates),
            'validation_scores_pp': {str(k):v for k,v in scores.items()} if frozen_alpha is None else {},
            'training_dates': fitted_dates,
            'validation_dates': sorted(evaluation_rows.voting_date.dt.strftime('%Y-%m-%d').unique().tolist()) if frozen_alpha is None else [],
            'preprocessing': 'training-only median imputation, scaling, categorical encoding; all-feature missingness indicators',
            'training_history_cold_start_share': .5, 'training_history_fallback': 'admissible earlier training-only global mean; 0.5 prior if empty',
            'sklearn_version': sklearn.__version__, 'training_rows': max((window.get('training_rows',0) for window in window_manifest),default=0),
            'training_design_sha256': hashlib.sha256('|'.join(window.get('training_design_sha256','')
                for window in window_manifest).encode()).hexdigest(),
            'features': numeric+categorical,
            'selection': 'frozen alpha; no evaluation targets used in fitting/selection' if frozen_alpha is not None else 'aggregate chronological expanding-window validation; scores used for selection',
            'refit_schedule': 'one estimator and preprocessing fit at each validation-window boundary; no within-window refit',
            'windows': window_manifest}
    return pd.DataFrame(output), manifest

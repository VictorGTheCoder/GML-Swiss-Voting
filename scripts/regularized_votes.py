"""Chronological regularized references over admissible prepared features."""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.impute import MissingIndicator, SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def historical_features(rows, config):
    design = pd.DataFrame(index=rows.index, columns=['municipal_history','history_missing'], dtype=float)
    for index, target in rows.iterrows():
        refit = config.mode == 'final_test' and config.refit_train_validation
        partitions = ['train','validation'] if refit or (config.history_policy == 'rolling' and target.partition != 'train') else ['train']
        if config.history_policy == 'rolling' and target.partition == 'test':
            partitions.append('test')
        past = rows.loc[rows.partition.isin(partitions) & rows.voting_date.lt(target.voting_date)
                        & rows.result_available_at.le(target.forecast_at)
                        & rows.result_availability_evidence.notna()
                        & rows.result_availability_evidence.astype(str).str.strip().ne('')]
        local = past.loc[past.municipality_id.eq(target.municipality_id) & past.geography_id.eq(target.geography_id)]
        fallback_pool = past.loc[past.partition.eq('train')]
        fallback = float(fallback_pool.target_share.mean()) if not fallback_pool.empty else .5
        design.loc[index] = [float(local.target_share.mean()) if not local.empty else fallback, float(local.empty)]
    return design


def _pipeline(numeric, categorical, alpha):
    transforms = [('numeric', Pipeline([('impute', SimpleImputer(strategy='median', keep_empty_features=True)),
                                       ('scale',StandardScaler())]), numeric)]
    transforms.append(('missingness', MissingIndicator(features='all',error_on_new=False), numeric+categorical))
    if categorical:
        transforms.append(('categorical', Pipeline([('impute',SimpleImputer(strategy='constant',fill_value='missing',keep_empty_features=True)),
                                                    ('encode',OneHotEncoder(handle_unknown='ignore',sparse_output=False))]), categorical))
    return Pipeline([('prepare',ColumnTransformer(transforms)), ('ridge',Ridge(alpha=alpha))])


def regularized_predictions(rows, config, baseline, design, blocks):
    partition = 'test' if config.mode == 'final_test' else 'validation'
    keys = set(zip(baseline.municipality_id,baseline.vote_id))
    evaluation = rows.loc[rows.partition.eq(partition) & pd.Series([(m,v) in keys for m,v in zip(rows.municipality_id,rows.vote_id)],index=rows.index)]
    expected_models = ['ridge_history'] + [f'ridge_{block.block_id}' for block in blocks]
    if config.mode == 'final_test' and (not config.selected_ridge_alphas or any(name not in config.selected_ridge_alphas for name in expected_models)):
        raise ValueError('Final test requires selected_ridge_alphas for every regularized model')
    if not config.ridge_alphas or any(not np.isfinite(alpha) or alpha <= 0 for alpha in config.ridge_alphas):
        raise ValueError('ridge_alphas must be finite positive candidates')
    if evaluation.empty:
        return pd.DataFrame(columns=baseline.columns), {}
    fitting_partitions = ['train','validation'] if config.mode == 'final_test' and config.refit_train_validation else ['train']
    train = rows.loc[rows.partition.isin(fitting_partitions) & rows.result_available_at.le(evaluation.forecast_at.min())
                     & rows.result_availability_evidence.notna()
                     & rows.result_availability_evidence.astype(str).str.strip().ne('')]
    if train.empty:
        return pd.DataFrame(columns=baseline.columns), {}
    feature_sets = {'ridge_history': (['municipal_history','history_missing'],[])}
    for block in blocks:
        feature_sets[f'ridge_{block.block_id}'] = (['municipal_history','history_missing'] + [f'{block.block_id}__{name}' for name in block.numeric_features],
                                                  [f'{block.block_id}__{name}' for name in block.categorical_features])
    output, manifest = [], {}
    for name, (numeric,categorical) in feature_sets.items():
        scores, fits = {}, {}
        frozen_alpha = config.selected_ridge_alphas.get(name) if config.selected_ridge_alphas else None
        if frozen_alpha is not None and (not np.isfinite(frozen_alpha) or frozen_alpha <= 0):
            raise ValueError('selected_ridge_alphas must be finite positive values')
        candidates = (frozen_alpha,) if frozen_alpha is not None else config.ridge_alphas
        matrix = design[numeric+categorical].copy()
        for column in categorical:
            matrix[column] = matrix[column].where(matrix[column].notna(),np.nan)
        for alpha in candidates:
            fit = _pipeline(numeric,categorical,alpha)
            fit.fit(matrix.loc[train.index],train.target_share)
            prediction = np.clip(fit.predict(matrix.loc[evaluation.index]),0,1)
            if frozen_alpha is None:
                scores[alpha] = float(np.mean(np.abs(prediction-evaluation.target_share))*100)
            fits[alpha] = (fit,prediction)
        selected = frozen_alpha if frozen_alpha is not None else min(scores,key=lambda alpha:(scores[alpha],alpha))
        fit,prediction = fits[selected]
        for (_,row),value in zip(evaluation.iterrows(),prediction):
            output.append({**row.to_dict(),'model':name,'prediction':float(value),'fallback':False})
        manifest[name] = {'selected_alpha': selected, 'validation_scores_pp': {str(k):v for k,v in scores.items()},
                          'training_dates': sorted(train.voting_date.dt.strftime('%Y-%m-%d').unique().tolist()),
                          'validation_dates': sorted(evaluation.voting_date.dt.strftime('%Y-%m-%d').unique().tolist()) if frozen_alpha is None else [],
                          'preprocessing': 'training-only median imputation, scaling, categorical encoding; all-feature missingness indicators',
                          'training_history_cold_start_share': .5, 'training_history_fallback': 'admissible earlier training-only global mean; 0.5 prior if empty',
                          'sklearn_version': sklearn.__version__, 'training_rows': len(train), 'training_design_sha256': hashlib.sha256(matrix.loc[train.index].to_json(orient='split').encode()).hexdigest(), 'features': numeric+categorical,
                          'selection': 'frozen alpha; no evaluation targets used in fitting/selection' if frozen_alpha is not None else 'chronological validation; reported scores used for selection'}
    return pd.DataFrame(output,columns=baseline.columns), manifest

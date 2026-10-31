"""Paired date-level uncertainty and explicit validation-to-final experiment freezing."""
from __future__ import annotations

import hashlib
import itertools
import json

import numpy as np
import pandas as pd

TEXT_POLICY = {
    'summary_field': 'summary_official', 'language': 'fr',
    'ngram_range': [1, 2], 'norm': 'l2', 'min_df': 2,
    'max_df': 0.95, 'max_features': 2000,
}


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()


def paired_uncertainty(predictions, *, seed, replicates):
    if not isinstance(replicates,int) or replicates < 1:
        raise ValueError('bootstrap_replicates must be a positive integer')
    results = []
    for left,right in itertools.combinations(sorted(predictions.model.unique()),2):
        columns = ['municipality_id','vote_id','voting_date','target_share','prediction']
        if 'evaluation_weight' in predictions:
            columns += ['evaluation_weight']
        a = predictions.loc[predictions.model.eq(left),columns]
        b = predictions.loc[predictions.model.eq(right),columns]
        paired = a.merge(b,on=['municipality_id','vote_id'],suffixes=('_left','_right'),validate='one_to_one')
        if paired.empty:
            continue
        if not paired.voting_date_left.eq(paired.voting_date_right).all() or not paired.target_share_left.eq(paired.target_share_right).all():
            raise ValueError('Paired predictions must share dates and targets')
        paired['left_error'] = (paired.prediction_left-paired.target_share_left).abs()*100
        paired['right_error'] = (paired.prediction_right-paired.target_share_right).abs()*100
        paired['weight'] = pd.to_numeric(paired.get('evaluation_weight_left',pd.Series(np.nan,index=paired.index)),errors='coerce')
        paired.loc[~np.isfinite(paired.weight) | paired.weight.le(0),'weight'] = 0.
        paired['weighted_left'] = paired.left_error*paired.weight
        paired['weighted_right'] = paired.right_error*paired.weight
        date_groups = paired.groupby('voting_date_left',sort=True).agg(
            rows=('vote_id','size'), left=('left_error','sum'), right=('right_error','sum'),
            weight=('weight','sum'), weighted_left=('weighted_left','sum'), weighted_right=('weighted_right','sum'))
        draw = np.random.default_rng(seed).integers(0,len(date_groups),size=(replicates,len(date_groups)))
        totals = date_groups.to_numpy()[draw].sum(axis=1)
        differences = (totals[:,2]-totals[:,1])/totals[:,0]
        weighted = np.divide(totals[:,5]-totals[:,4],totals[:,3],out=np.full(replicates,np.nan),where=totals[:,3]>0)
        dates = date_groups.index.strftime('%Y-%m-%d').tolist()
        total_weight = float(date_groups.weight.sum())
        results.append({'left_model':left,'right_model':right,'paired_rows':len(paired),
            'paired_objects':int(paired.vote_id.nunique()),'paired_dates':len(date_groups),
            'difference_mae_pp':float(paired.right_error.mean()-paired.left_error.mean()),
            'ci95_mae_difference_pp':np.quantile(differences,[.025,.975]).tolist() if len(date_groups)>1 else None,
            'interval_status':'exploratory' if len(date_groups)>1 else 'insufficient_dates',
            'weighted_difference_mae_pp':float((paired.weighted_right.sum()-paired.weighted_left.sum())/total_weight) if total_weight else None,
            'ci95_weighted_difference_pp':np.nanquantile(weighted,[.025,.975]).tolist() if len(date_groups)>1 and np.isfinite(weighted).any() else None,
            'seed':seed,'replicates':replicates,'direction':'right minus left; negative favors right',
            'resampling_unit':'complete held-out voting date; paired observations retained',
            'sampling_audit':[{'dates':[dates[i] for i in indices],'sampled_rows':int(totals[position,0])}
                              for position,indices in enumerate(draw[:3])],
            'limitations':'Few held-out dates can make intervals unstable; resampling dates does not account for possible serial dependence. Selection scores remain subject to model-selection optimism.'})
    return results


def experiment_signature(manifest):
    config = manifest['experiment_configuration'].copy()
    for key in ['mode','choices_frozen','selected_ridge_alphas','selected_hist_gradient_boosting']:
        config.pop(key,None)
    windows = [list(window) for window in (config.get('validation_windows') or [config['validation_dates']])]
    blocks = manifest['feature_blocks']
    block_ids = sorted(blocks)
    selected_families = {
        'baselines': ['constant', 'municipal_history'],
        'ridge': ['ridge_history'] + [f'ridge_{block_id}' for block_id in block_ids],
        'hist_gradient_boosting': bool(block_ids),
        'paired_text': (['paired_nontext', 'paired_text']
            if manifest.get('text_records_requested', False) else []),
    }
    return {'configuration':config,'implementation_sha256':manifest['implementation_sha256'],
            'versions':manifest['versions'],'source_versions':manifest['source_versions'],
            'geography':manifest['geography'],'feature_blocks':manifest['feature_blocks'],
            'forecast_cutoffs':manifest['forecast_cutoffs'],'partition_keys_sha256':manifest['partition_keys_sha256'],
            'prepared_availability_sha256':manifest['prepared_availability_sha256'],
            'pretest_labels_sha256':manifest['pretest_labels_sha256'],
            'computed_history_signature':manifest.get('computed_history_signature'),
            'text_records_sha256':manifest.get('text_records_sha256'),
            'validation_windows':windows,
            'final_refit_schedule':('training_plus_validation_before_first_test_forecast'
                if config.get('refit_train_validation') else 'training_only_before_first_test_forecast'),
            'selected_model_families':selected_families,
            'text_policy':TEXT_POLICY}


def freeze_experiment(validation_result):
    manifest = validation_result['manifest']
    if manifest['mode'] != 'validation':
        raise ValueError('Only a validation run may freeze experiment choices')
    skipped_regularized = sorted(name for name, run in manifest['regularized'].items()
                                 if run.get('status') in ('no_evaluable_windows', 'skipped'))
    evaluated_regularized = {name: run for name, run in manifest['regularized'].items()
                             if name not in skipped_regularized}
    if any(run.get('selected_alpha') is None for run in evaluated_regularized.values()):
        raise ValueError('Cannot freeze a Ridge model without an evaluated selected_alpha')
    selected = {name: run['selected_alpha'] for name, run in evaluated_regularized.items()}
    text = validation_result.get('text_experiment') or {}
    selected.update({name:run['selected_alpha'] for name,run in text.get('models',{}).items()})
    boosting = {name:run['settings'] for name,run in manifest.get('hist_gradient_boosting',{}).items()
                if run.get('status') == 'evaluated' and run.get('settings') is not None}
    frozen = {'schema_version':2,'signature':experiment_signature(manifest),
              'selected_ridge_alphas':selected,
              'selected_hist_gradient_boosting':boosting,
              'skipped_regularized': skipped_regularized,
              'nontext_choices':{name:{key:run[key] for key in ['selected_alpha','features','preprocessing']}
                                 for name,run in evaluated_regularized.items()},
              'text_choices':{'status':text.get('status','not_requested'),'models':text.get('models',{}),
                              'representation_settings':text.get('representation',{}).get('settings',{})},
              'validation_metrics':validation_result['metrics'],
              'selection_judgment':('Prefer Ridge unless nonlinear validation improvements are consistent '
                  'and supported by paired date errors and uncertainty; this is a documented judgment, '
                  'not an automatic significance threshold.'),
              'final_policy':'Only declared fit periods; no test-driven fitting or selection'}
    frozen['sha256'] = _digest(frozen)
    return frozen


def verify_frozen_experiment(manifest,frozen):
    if frozen.get('schema_version') != 2:
        raise ValueError('Unsupported frozen experiment schema')
    payload = {key:value for key,value in frozen.items() if key != 'sha256'}
    if frozen.get('sha256') != _digest(payload):
        raise ValueError('frozen experiment integrity check failed')
    if _digest(experiment_signature(manifest)) != _digest(frozen['signature']):
        raise ValueError('Run sources, features, partitions or configuration differ from frozen experiment')
    if _digest(manifest['selected_ridge_alphas'] or {}) != _digest(frozen['selected_ridge_alphas']):
        raise ValueError('Run alphas differ from frozen experiment')
    if _digest(manifest.get('selected_hist_gradient_boosting') or {}) != _digest(
            frozen.get('selected_hist_gradient_boosting') or {}):
        raise ValueError('Run histogram gradient boosting settings differ from frozen experiment')

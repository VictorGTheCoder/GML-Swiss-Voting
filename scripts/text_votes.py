"""Paired additive brochure text experiment over the evaluation's admitted rows."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from scipy.sparse import csr_matrix, hstack

from scripts.federal_explanations_temporal import build_forecast_text_export
from scripts.regularized_votes import _pipeline, historical_features


def text_experiment(rows, config, baseline, design, blocks, records):
    export = build_forecast_text_export(records)
    documents = {}
    mismatches = []
    for document in export['documents']:
        vote = str(document['vote_id'])
        group = rows.loc[rows.vote_id.eq(vote)]
        if group.empty:
            continue
        if (pd.to_datetime(document['forecast_at'], utc=True, errors='coerce') != group.forecast_at.iloc[0]
                or pd.to_datetime(document['voting_date'], utc=True, errors='coerce') != group.voting_date.iloc[0]):
            mismatches.append(vote)
        else:
            documents[vote] = document
    partition = 'test' if config.mode == 'final_test' else 'validation'
    baseline_keys = set(zip(baseline.municipality_id, baseline.vote_id))
    wider = rows.loc[rows.partition.eq(partition) & pd.Series(
        [(m,v) in baseline_keys for m,v in zip(rows.municipality_id, rows.vote_id)], index=rows.index)]
    paired = wider.loc[wider.vote_id.isin(documents)]
    def counts(frame):
        return {'rows': len(frame), 'objects': int(frame.vote_id.nunique()), 'dates': int(frame.voting_date.nunique())}
    result = {'status': 'skipped', 'reason': 'empty eligible training or evaluation text corpus',
        'export_report': export['report'], 'excluded_documents': export['exclusions'],
        'forecast_or_date_mismatches': mismatches,
        'coverage': {'wider_nontext': counts(wider), 'paired': counts(paired),
                     'lost_rows': len(wider)-len(paired),
                     'lost_objects': int(wider.vote_id.nunique()-paired.vote_id.nunique())},
        'interpretation': 'Additive text shifts are shared across municipalities for an object before prediction clipping.',
        'predictions': pd.DataFrame(), 'metrics': {}, 'by_object': [], 'by_date': []}
    if paired.empty:
        return result
    train = rows.loc[rows.partition.eq('train') & rows.vote_id.isin(documents)
        & rows.result_available_at.le(paired.forecast_at.min())
        & rows.result_availability_evidence.notna()
        & rows.result_availability_evidence.astype(str).str.strip().ne('')]
    if train.empty:
        return result
    objects = sorted(train.vote_id.unique())
    vectorizer = TfidfVectorizer()
    try:
        object_vectors = vectorizer.fit_transform([documents[vote]['text'] for vote in objects])
    except ValueError as error:
        if 'empty vocabulary' not in str(error):
            raise
        result['reason'] = 'eligible training text contains no vocabulary tokens'
        return result
    result['representation'] = {'training_objects': objects,
        'vocabulary': sorted(vectorizer.vocabulary_, key=vectorizer.vocabulary_.get),
        'idf': vectorizer.idf_.tolist(), 'training_vectors': object_vectors.toarray().tolist(),
        'documents': [{key: documents[vote].get(key) for key in
            ['vote_id','source_sha256','forecast_at','language']} for vote in objects],
        'settings': {'lowercase': True, 'token_pattern': vectorizer.token_pattern,
                     'norm': 'l2', 'smooth_idf': True, 'sublinear_tf': False}}
    text_train = object_vectors[[objects.index(vote) for vote in train.vote_id]]
    text_eval = vectorizer.transform([documents[vote]['text'] for vote in paired.vote_id])
    if design.empty:
        design = historical_features(rows, config)
    numeric = ['municipal_history','history_missing'] + [f'{b.block_id}__{n}' for b in blocks for n in b.numeric_features]
    categorical = [f'{b.block_id}__{n}' for b in blocks for n in b.categorical_features]
    preprocess = _pipeline(numeric, categorical, 1.).named_steps['prepare']
    matrix = design[numeric+categorical].copy()
    for column in categorical:
        matrix[column] = matrix[column].where(matrix[column].notna(), np.nan)
    base_train = csr_matrix(preprocess.fit_transform(matrix.loc[train.index]))
    base_eval = csr_matrix(preprocess.transform(matrix.loc[paired.index]))
    selected, predictions = {}, []
    for name, xtrain, xeval in [('paired_nontext',base_train,base_eval),
            ('paired_text',hstack([base_train,text_train]),hstack([base_eval,text_eval]))]:
        frozen = (config.selected_ridge_alphas or {}).get(name)
        if config.mode == 'final_test' and frozen is None:
            raise ValueError('Final text experiment requires selected_ridge_alphas for paired_nontext and paired_text')
        candidates = (frozen,) if frozen is not None else config.ridge_alphas
        if not candidates or any(not np.isfinite(a) or a <= 0 for a in candidates):
            raise ValueError('Text ridge alphas must be finite positive values')
        fits, scores = {}, {}
        for alpha in candidates:
            fit = Ridge(alpha=alpha, solver='lsqr').fit(xtrain, train.target_share)
            prediction = np.clip(fit.predict(xeval), 0, 1)
            fits[alpha] = prediction
            if frozen is None:
                scores[alpha] = float(np.abs(prediction-paired.target_share).mean()*100)
        alpha = frozen if frozen is not None else min(scores, key=lambda a:(scores[a],a))
        selected[name] = {'selected_alpha': alpha, 'validation_scores_pp': {str(a):s for a,s in scores.items()},
            'training': counts(train), 'features': numeric+categorical,
            'selection': 'frozen; no held-out targets' if frozen is not None else 'chronological validation'}
        for (_, row), value in zip(paired.iterrows(),fits[alpha]):
            predictions.append({**row.to_dict(), 'model': name, 'prediction':float(value)})
    result.update(status='evaluated', reason=None, models=selected, predictions=pd.DataFrame(predictions))
    for name, group in result['predictions'].groupby('model'):
        def score(frame):
            return {**counts(frame), 'mae_pp':float((frame.prediction-frame.target_share).abs().mean()*100)}
        result['metrics'][name] = score(group)
        for vote, subgroup in group.groupby('vote_id'):
            result['by_object'].append({'model':name, 'vote_id':vote, **score(subgroup)})
        for date, subgroup in group.groupby('voting_date'):
            result['by_date'].append({'model':name, 'voting_date':str(date), **score(subgroup)})
    return result

"""Paired additive brochure text experiment over the evaluation's admitted rows."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from scipy.sparse import csr_matrix, hstack

from scripts.modeling.expanding_windows import select_training_rows, window_dates
from scripts.modeling.forecast_text_export import build_forecast_text_export
from scripts.modeling.final_evaluation import TEXT_POLICY
from scripts.modeling.regularized_votes import _pipeline, historical_features


def text_experiment(rows, config, baseline, design, blocks, records):
    export = build_forecast_text_export(records, text_field=TEXT_POLICY['summary_field'])
    documents = {}
    known_objects = set(rows.vote_id)
    mismatches = list(dict.fromkeys(str(record.get('vote_id')) for record in export['exclusions']
        if str(record.get('vote_id')) in known_objects and any(reason in record['exclusion_reason'] for reason in
            ['voting date is invalid','forecast cutoff is not before voting day'])))
    for document in export['documents']:
        vote = str(document['vote_id'])
        group = rows.loc[rows.vote_id.eq(vote)]
        if group.empty:
            continue
        if (pd.to_datetime(document['forecast_at'], utc=True, errors='coerce') != group.forecast_at.iloc[0]
                or pd.to_datetime(document['voting_date'], utc=True, errors='coerce') != group.voting_date.iloc[0]):
            mismatches.append(vote)
        elif document.get('text_source_field') == TEXT_POLICY['summary_field']:
            documents[vote] = document
    languages = sorted({str(doc.get('language') or '').strip().lower() for doc in documents.values()})
    selected_language = TEXT_POLICY['language'] if TEXT_POLICY['language'] in languages else None
    language_exclusions = sorted(vote for vote, doc in documents.items()
        if selected_language is None or str(doc.get('language') or '').strip().lower() != selected_language)
    documents = {vote: doc for vote, doc in documents.items() if vote not in language_exclusions}
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
        'language': selected_language, 'available_languages': languages,
        'language_exclusions': language_exclusions,
        'coverage': {'wider_nontext': counts(wider), 'paired': counts(paired),
                     'lost_rows': len(wider)-len(paired),
                     'lost_objects': int(wider.vote_id.nunique()-paired.vote_id.nunique())},
        'interpretation': 'Additive text shifts are shared across municipalities for an object before prediction clipping.',
        'predictions': pd.DataFrame(), 'metrics': {}, 'by_object': [], 'by_date': []}
    if selected_language is None:
        if export['documents']:
            result['reason'] = 'preferred French language is unavailable in validated summaries'
            result['language_status'] = 'prerequisite_unresolved'
        else:
            result['reason'] = 'no eligible validated official summaries are available'
            result['summary_status'] = 'prerequisite_unresolved'
        return result
    if paired.empty:
        if language_exclusions:
            result['reason'] = 'no selected-language summaries cover eligible evaluation objects'
        return result
    if design.empty:
        design = historical_features(rows, config)
    blocks = tuple(block for block in blocks if block.prerequisite_reason is None)
    numeric = ['municipal_history','history_missing'] + [f'{b.block_id}__{n}' for b in blocks for n in b.numeric_features]
    categorical = [f'{b.block_id}__{n}' for b in blocks for n in b.categorical_features]
    preprocess = _pipeline(numeric, categorical, 1.).named_steps['prepare']
    matrix = design[numeric+categorical].copy()
    for column in categorical:
        matrix[column] = matrix[column].where(matrix[column].notna(), np.nan)
    declared_windows = window_dates(config, partition)
    window_eval_frames = []
    for dates in declared_windows:
        window_eval_frames.append(paired.loc[paired.voting_date.isin(dates)])
    if not any(len(frame) for frame in window_eval_frames):
        return result
    if design.empty:
        design = historical_features(rows, config)
    selected, predictions, fold_reports = {}, [], []
    for index, window_eval in enumerate(window_eval_frames):
        if window_eval.empty:
            fold_reports.append({'window': index+1, 'status': 'no_eligible_evaluation_rows',
                'validation_dates': declared_windows[index].strftime('%Y-%m-%d').tolist()})
            continue
        first_forecast = window_eval.forecast_at.min()
        train = select_training_rows(rows, config, partition, declared_windows,
            index, first_forecast, eligible_vote_ids=documents)
        if train.empty:
            fold_reports.append({'window': index+1, 'status': 'no_published_training_summaries',
                'validation_dates': sorted(window_eval.voting_date.dt.strftime('%Y-%m-%d').unique().tolist()),
                'training_dates': [], 'training_row_keys': [],
                'validation_row_keys': list(map(list, zip(window_eval.municipality_id,window_eval.vote_id)))})
            continue
        objects = sorted(train.vote_id.unique())
        initial_min_df = TEXT_POLICY['min_df']
        effective_min_df = 1 if len(objects) < initial_min_df else initial_min_df
        initial_max_df = TEXT_POLICY['max_df']
        effective_max_df = 1.0 if initial_max_df * len(objects) < effective_min_df else initial_max_df
        vectorizer = TfidfVectorizer(ngram_range=tuple(TEXT_POLICY['ngram_range']),
            norm=TEXT_POLICY['norm'], min_df=effective_min_df,
            max_df=effective_max_df, max_features=TEXT_POLICY['max_features'])
        try:
            object_vectors = vectorizer.fit_transform([documents[vote]['text'] for vote in objects])
        except ValueError as error:
            if not any(message in str(error) for message in ['empty vocabulary', 'no terms remain']):
                raise
            fold_reports.append({'window': index+1, 'status': 'empty_vocabulary',
                'reason': 'eligible training summaries contain no vocabulary after TF-IDF frequency filters',
                'training_objects': objects, 'training_dates': sorted(train.voting_date.dt.strftime('%Y-%m-%d').unique().tolist()),
                'validation_dates': sorted(window_eval.voting_date.dt.strftime('%Y-%m-%d').unique().tolist())})
            continue
        fold = {'window': index+1, 'status': 'evaluated', 'training_objects': objects,
            'training_dates': sorted(train.voting_date.dt.strftime('%Y-%m-%d').unique().tolist()),
            'training_row_keys': list(map(list, zip(train.municipality_id,train.vote_id))),
            'validation_dates': sorted(window_eval.voting_date.dt.strftime('%Y-%m-%d').unique().tolist()),
            'validation_row_keys': list(map(list, zip(window_eval.municipality_id,window_eval.vote_id))),
            'first_forecast_at': str(first_forecast),
            'fit_cutoff': str(train.result_available_at.max()),
            'refit_schedule': 'fit vectorizer, preprocessing and estimator once at window start; fixed within window',
            'tfidf': {'ngram_range': TEXT_POLICY['ngram_range'], 'norm': TEXT_POLICY['norm'], 'min_df': effective_min_df,
                'max_df': effective_max_df, 'initial_max_df': initial_max_df,
                'max_features': TEXT_POLICY['max_features'],
                'initial_min_df': initial_min_df,
                'adjustment': ('min_df reduced to 1 because fewer than two unique training objects were available'
                    if effective_min_df != initial_min_df else None),
                'max_df_adjustment': ('max_df increased to 1.0 because the proposed maximum-frequency cutoff '
                    'is below the minimum-frequency cutoff for this training corpus'
                    if effective_max_df != initial_max_df else None),
                'training_object_count': len(objects),
                'vocabulary': sorted(vectorizer.vocabulary_, key=vectorizer.vocabulary_.get),
                'idf': vectorizer.idf_.tolist(),
                'training_vectors': object_vectors.toarray().tolist()},
            'documents': [{key: documents[vote].get(key) for key in
                ['vote_id','source_sha256','forecast_at','language','text_source_field']} for vote in objects]}
        text_train = object_vectors[[objects.index(vote) for vote in train.vote_id]]
        text_eval = vectorizer.transform([documents[vote]['text'] for vote in window_eval.vote_id])
        current_preprocess = _pipeline(numeric, categorical, 1.).named_steps['prepare']
        base_train = csr_matrix(current_preprocess.fit_transform(matrix.loc[train.index]))
        base_eval = csr_matrix(current_preprocess.transform(matrix.loc[window_eval.index]))
        for name, xtrain, xeval in [('paired_nontext',base_train,base_eval),
                ('paired_text',hstack([base_train,text_train]),hstack([base_eval,text_eval]))]:
            frozen = (config.selected_ridge_alphas or {}).get(name)
            if config.mode == 'final_test' and frozen is None:
                raise ValueError('Final text experiment requires selected_ridge_alphas for paired_nontext and paired_text')
            candidates = (frozen,) if frozen is not None else config.ridge_alphas
            if not candidates or any(not np.isfinite(a) or a <= 0 for a in candidates):
                raise ValueError('Text ridge alphas must be finite positive values')
            # Retain candidate-specific fold predictions until aggregate chronological
            # validation has selected one alpha per paired model.
            candidate_store = selected.setdefault(name, {'frozen': frozen, 'candidates': candidates, 'frames': {a: [] for a in candidates}})
            if candidate_store['frozen'] != frozen or tuple(candidate_store['candidates']) != tuple(candidates):
                raise ValueError('Text alpha candidates must remain fixed across shared windows')
            for alpha in candidates:
                fit = Ridge(alpha=alpha, solver='lsqr').fit(xtrain, train.target_share)
                raw_prediction = fit.predict(xeval)
                frame = window_eval.copy()
                frame['model'] = name
                frame['raw_prediction'] = raw_prediction.astype(float)
                frame['prediction'] = np.clip(raw_prediction,0,1).astype(float)
                frame['clipped'] = ~np.isclose(raw_prediction,frame.prediction)
                frame['validation_window'] = index+1
                candidate_store['frames'][alpha].append(frame)
        fold_reports.append(fold)
    model_reports = {}
    for name, store in selected.items():
        scores = {}
        for alpha, frames in store['frames'].items():
            joined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
            scores[alpha] = (float(np.abs(joined.prediction-joined.target_share).mean()*100)
                if len(joined) and store['frozen'] is None else None)
        available = {alpha: score for alpha,score in scores.items() if score is not None}
        frozen = store['frozen']
        if not available and frozen is None:
            continue
        alpha = frozen if frozen is not None else min(available,key=lambda a:(available[a],a))
        if alpha not in store['frames'] or not store['frames'][alpha]:
            raise ValueError('Selected text Ridge alpha has no evaluable shared window')
        model_reports[name] = {'selected_alpha': alpha,
            'validation_scores_pp': {str(a):score for a,score in scores.items()} if frozen is None else {},
            'selection': 'frozen alpha; no held-out targets used' if frozen is not None else 'aggregate chronological validation',
            'features': numeric+categorical,
            'training': {'rows': len({tuple(key) for fold in fold_reports for key in fold.get('training_row_keys', [])}),
                'objects': len({key[1] for fold in fold_reports for key in fold.get('training_row_keys', [])}),
                'dates': len({date for fold in fold_reports for date in fold.get('training_dates', [])})},
            'refit_schedule': 'one estimator and preprocessing fit at each shared window boundary; no within-window refit'}
    # Flatten the per-window prediction frames retained above.
    prediction_frames = []
    for name, store in selected.items():
        report = model_reports.get(name)
        if report is not None:
            prediction_frames.extend(store['frames'][report['selected_alpha']])
    prediction_frame = pd.concat(prediction_frames, ignore_index=True) if prediction_frames else pd.DataFrame()
    result['windows'] = fold_reports
    if fold_reports and not any(fold.get('status') == 'evaluated' for fold in fold_reports):
        result['reason'] = 'no shared validation window has eligible training summaries and vocabulary'
        return result
    representation = {'training_objects': sorted({vote for fold in fold_reports for vote in fold.get('training_objects', [])}),
        'language': selected_language, 'source_field': 'summary_official',
        'settings': {'lowercase': True, 'token_pattern': TfidfVectorizer().token_pattern,
            'ngram_range': [1,2], 'norm': 'l2', 'min_df': 2, 'max_df': 0.95,
            'max_features': 2000, 'smooth_idf': True, 'sublinear_tf': False},
        'folds': [fold.get('tfidf') for fold in fold_reports if fold.get('status') == 'evaluated']}
    if len(representation['folds']) == 1:
        representation.update(representation['folds'][0])
    result['representation'] = representation
    result.update(status='evaluated', reason=None, models=model_reports, predictions=prediction_frame)
    if prediction_frame.empty:
        result['status'] = 'skipped'
        result['reason'] = 'no paired predictions were produced by eligible shared windows'
        return result
    for name, group in result['predictions'].groupby('model'):
        def score(frame):
            from scripts.modeling.vote_metrics import score_predictions
            return {**counts(frame),**score_predictions(frame),'weight_origin':config.evaluation_weight_origin}
        result['metrics'][name] = score(group)
        for vote, subgroup in group.groupby('vote_id'):
            result['by_object'].append({'model':name, 'vote_id':vote, **score(subgroup)})
        for date, subgroup in group.groupby('voting_date'):
            result['by_date'].append({'model':name, 'voting_date':str(date), **score(subgroup)})
    return result


def synthetic_text_example(rows):
    """Illustrative reviewed-record fixture; no claims about real Swiss brochure evidence."""
    records = []
    for row in rows.drop_duplicates('vote_id').itertuples():
        forecast = str(pd.Timestamp(row.forecast_at,tz='UTC'))
        records.append(dict(vote_id=row.vote_id,voting_date=str(row.voting_date),forecast_at=forecast,
            forecast_evidence='synthetic-brochure-release',availability_at=forecast,
            availability_reference='synthetic-archive',availability_status='CONFIRMED_PRE_VOTE',
            source_sha256=f'synthetic-{row.vote_id}',decision_source_sha256=f'synthetic-{row.vote_id}',
            match_status='VALIDATED',extraction_status='EXTRACTED',semantic_status='VALIDATED',
            language='fr', summary_official='synthetic municipal history apples oranges' if row.vote_id == 'old' else 'synthetic heldout public policy bananas'))
    return records

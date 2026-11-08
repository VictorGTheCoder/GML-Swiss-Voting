"""Chronological retrospective comparisons of interactions and cold-start latent profiles."""
from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from scipy.sparse import csr_matrix, hstack
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from threadpoolctl import threadpool_limits

from scripts.common.config import ROOT
from scripts.integration.build_modeling_dataset import clean_outcomes
from scripts.modeling import block_selection as blocks
from scripts.modeling import retrospective_demo as demo

PARTIES = {'plr': 'fdp', 'pdc': 'cvp', 'ps': 'sps', 'udc': 'svp',
           'pev': 'evp', 'verts': 'gps', 'pvl': 'glp', 'pbd': 'bdp'}
RECOMMENDATIONS = [f'recommendation_{p}' for p in PARTIES]
CUES = [f'cue_{p}' for p in PARTIES]
THEMES = ['object_legal_form', 'object_domain_1']
LOCAL_NUMERIC = ['history_mean_yes'] + [f'party_share_{p}' for p in ['plr', 'ps', 'udc', 'verts']]
LOCAL_CATEGORICAL = ['language_region', 'urban_rural']
LATENT_DIMENSIONS = 3
CONTRASTS = {
    'theme_interactions': ('ridge_theme_interactions', 'ridge_combined'),
    'recommendations': ('ridge_recommendations', 'ridge_combined'),
    'local_recommendation_interactions': ('ridge_recommendation_interactions', 'ridge_recommendations'),
    'boosting_recommendations': ('boosting_recommendations', 'boosting_combined'),
    'latent_factors': ('latent_profiles', 'object_mean'),
    'boosting_vs_ridge': ('boosting_combined', 'ridge_combined'),
}


def attach_recommendations(data, source):
    """Join only explicit party allowlist, preserving unknown and non-binary codes."""
    required = ['vote_key', 'vote_date'] + [f'p-{p}' for p in PARTIES.values()]
    source = source[required].copy()
    if source.vote_key.isna().any() or source.duplicated('vote_key').any():
        raise ValueError('Recommendation source requires unique, nonnull vote keys')
    original_index = data.index
    joined = data.merge(source, on='vote_key', how='left', validate='many_to_one',
                        suffixes=('', '_recommendation'), indicator=True, sort=False)
    if not joined['_merge'].eq('both').all() or not joined.vote_date.eq(joined.vote_date_recommendation).all():
        raise ValueError('Recommendation object correspondence or dates disagree')
    joined.index = original_index
    for party, code in PARTIES.items():
        raw = pd.to_numeric(joined[f'p-{code}'], errors='raise')
        if not raw.dropna().isin([1, 2, 3, 4, 5, 8, 9, 66, 9999]).all():
            raise ValueError(f'Unknown recommendation code for {party}')
        joined[f'recommendation_{party}'] = raw.astype('Int64').astype('string')
        sign = raw.map({1: 1., 2: -1., 3: 0., 4: 0., 5: 0., 66: 0.})
        joined[f'cue_{party}'] = joined[f'party_share_{party}'].astype(float) * sign.astype(float)
    return joined.drop(columns=['_merge', 'vote_date_recommendation'] + [f'p-{p}' for p in PARTIES.values()])


def model_input(frame):
    x = demo.model_input(frame)
    for c in RECOMMENDATIONS:
        x[c] = frame[c].astype(object).where(frame[c].notna(), np.nan)
    for c in CUES:
        x[c] = frame[c].astype(float)
    return x


def categorical_encoder():
    return Pipeline([('impute', SimpleImputer(strategy='constant', fill_value='missing', keep_empty_features=True)),
                     ('encode', OneHotEncoder(handle_unknown='ignore', sparse_output=True))])


def theme_interactions(train, evaluation):
    """Encode explicit local × object terms; evaluation cannot change vocabulary/scales."""
    base = demo.ridge_pipeline(demo.NUMERIC + demo.INDICATORS, demo.CATEGORICAL, 1.).named_steps['prepare']
    local = demo.ridge_pipeline(LOCAL_NUMERIC, LOCAL_CATEGORICAL, 1.).named_steps['prepare']
    objects = categorical_encoder()
    bt, be = csr_matrix(base.fit_transform(train)), csr_matrix(base.transform(evaluation))
    lt, le = csr_matrix(local.fit_transform(train)), csr_matrix(local.transform(evaluation))
    ot, oe = objects.fit_transform(train[THEMES]).tocsc(), objects.transform(evaluation[THEMES]).tocsc()
    train_parts, eval_parts = [bt], [be]
    for j in range(ot.shape[1]):
        train_parts.append(lt.multiply(ot[:, j]))
        eval_parts.append(le.multiply(oe[:, j]))
    return hstack(train_parts, format='csr'), hstack(eval_parts, format='csr')


def object_rows(frame):
    columns = [c for c in demo.CATEGORICAL if c.startswith('object_')] + RECOMMENDATIONS
    if frame.groupby('vote_id')[columns].nunique(dropna=False).gt(1).any().any():
        raise ValueError('Object features must be identical across its municipalities')
    result = frame.drop_duplicates('vote_id').set_index('vote_id')[columns].astype(object)
    return result.where(result.notna(), np.nan)


def latent_predictions(train, evaluation, dimensions=LATENT_DIMENSIONS):
    """Learn territorial basis and mapping from object features on training objects only."""
    objects, future = object_rows(train), object_rows(evaluation)
    matrix = train.pivot(index='vote_id', columns='municipality_id', values='yes_share').reindex(objects.index)
    means = matrix.mean(axis=1).to_numpy(dtype=float)
    residuals = matrix.to_numpy(dtype=float) - means[:, None]
    missing = int(np.isnan(residuals).sum())
    residuals = np.nan_to_num(residuals, nan=0.)
    rank = min(dimensions, *residuals.shape)
    _, _, basis = np.linalg.svd(residuals, full_matrices=False)
    basis = basis[:rank]
    coefficients = residuals @ basis.T
    targets = np.column_stack([means, coefficients])
    encode = categorical_encoder()
    model = Ridge(alpha=1., solver='lsqr', tol=1e-6)
    model.fit(encode.fit_transform(objects), targets)
    estimates = model.predict(encode.transform(future))
    object_positions = future.index.get_indexer(evaluation.vote_id)
    municipality_positions = matrix.columns.get_indexer(evaluation.municipality_id)
    mean_prediction = estimates[object_positions, 0]
    predicted = mean_prediction.copy()
    known = municipality_positions >= 0
    predicted[known] += np.einsum('ij,ij->i', estimates[object_positions[known], 1:],
                                   basis[:, municipality_positions[known]].T)
    return mean_prediction, predicted, {
        'dimensions': rank, 'training_objects': len(objects), 'training_municipalities': len(matrix.columns),
        'missing_training_cells_centered_to_zero': missing,
        'unseen_evaluation_municipality_rows_fallback_to_object_mean': int((~known).sum()),
    }


def fit_window(train, evaluation, outcomes):
    train, evaluation = train.copy(), evaluation.copy()
    cutoff = train.vote_date.max()
    if cutoff >= evaluation.vote_date.min():
        raise ValueError('Training must precede evaluation')
    for frame in [train, evaluation]:
        history = demo.frozen_history(frame, outcomes, train_end=cutoff)
        frame[history.columns] = history
    xt, xe = model_input(train), model_input(evaluation)
    numeric, categorical = demo.NUMERIC + demo.INDICATORS, demo.CATEGORICAL
    specifications = {
        'ridge_history': (blocks.HISTORY, []), 'ridge_combined': (numeric, categorical),
        'ridge_recommendations': (numeric, categorical + RECOMMENDATIONS),
        'ridge_recommendation_interactions': (numeric + CUES, categorical + RECOMMENDATIONS),
    }
    raw, details = {}, {}
    with threadpool_limits(limits=1):
        for name, (num, cat) in specifications.items():
            model = demo.ridge_pipeline(num, cat, 1.)
            model.fit(xt, train.yes_share.astype(float))
            raw[name] = model.predict(xe)
            details[name] = {'transformed_features': len(model.named_steps['prepare'].get_feature_names_out())}
        a, b = theme_interactions(xt, xe)
        ridge = Ridge(alpha=1., solver='lsqr', tol=1e-6).fit(a, train.yes_share.astype(float))
        raw['ridge_theme_interactions'] = ridge.predict(b)
        details['ridge_theme_interactions'] = {'transformed_features': a.shape[1], 'solver': 'lsqr', 'tol': 1e-6}
        for name, use_recommendations in [('boosting_combined', False), ('boosting_recommendations', True)]:
            # Reuse the demo's exact fixed settings and categorical encoding.
            from sklearn.compose import ColumnTransformer
            from sklearn.ensemble import HistGradientBoostingRegressor
            from sklearn.preprocessing import OrdinalEncoder
            num = [c for c in numeric if not xt[c].isna().all()]
            cat = [c for c in categorical + (RECOMMENDATIONS if use_recommendations else [])
                   if not xt[c].isna().all()]
            _, _, settings = demo.notebook_pipeline(xt)
            prepare = ColumnTransformer([
                ('numeric', 'passthrough', num),
                ('categorical', OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=np.nan,
                                              encoded_missing_value=np.nan), cat)], sparse_threshold=0)
            model = Pipeline([('prepare', prepare), ('model', HistGradientBoostingRegressor(
                **settings, categorical_features=[False] * len(num) + [True] * len(cat)))])
            model.fit(xt, train.yes_share.astype(float))
            raw[name] = model.predict(xe)
            details[name] = {'settings': settings, 'numeric': num, 'categorical': cat}
        mean, latent, latent_details = latent_predictions(train, evaluation)
        raw['object_mean'], raw['latent_profiles'] = mean, latent
        details['latent_profiles'] = latent_details
    records = []
    for name, values in raw.items():
        if not np.isfinite(values).all():
            raise ValueError(f'Nonfinite predictions: {name}')
        result = evaluation[['municipality_id', 'vote_id', 'vote_date', 'yes_share']].rename(
            columns={'yes_share': 'target_share'}).copy()
        result['model'], result['raw_prediction'] = name, values
        result['prediction'] = np.clip(values, 0, 1)
        result['clipped'] = values != result.prediction
        records.append(result)
    coverage = []
    for partition, frame in [('train', train), ('evaluation', evaluation)]:
        for c in RECOMMENDATIONS + CUES:
            coverage.append({'partition': partition, 'feature': c, 'rows': len(frame),
                             'missing_share': frame[c].isna().mean(),
                             'objects': frame.vote_id.nunique(), 'dates': frame.vote_date.nunique()})
    return pd.concat(records, ignore_index=True), details, pd.DataFrame(coverage)


def paired_gains(table, keys, value, reference='ridge_combined'):
    baseline = table.loc[table.model.eq(reference), keys + [value]]
    results = []
    for name, candidate in table.groupby('model', sort=False):
        paired = candidate.merge(baseline, on=keys, suffixes=('', '_reference'), how='outer',
                                 validate='one_to_one', indicator=True)
        if not paired['_merge'].eq('both').all():
            raise ValueError('Models must use identical evaluation units')
        paired['gain_pp'] = paired[f'{value}_reference'] - paired[value]
        paired['model'] = name
        results.append(paired.drop(columns='_merge'))
    return pd.concat(results, ignore_index=True)


def evaluate(data, outcomes, years=blocks.EVALUATION_YEARS):
    predictions, windows, coverage = [], [], []
    for year, train, evaluation in blocks.chronological_windows(data, years):
        print(f'Window {year}: {train.vote_id.nunique()} train / {evaluation.vote_id.nunique()} evaluation objects', flush=True)
        predicted, details, observed = fit_window(train, evaluation, outcomes)
        predictions.append(predicted.assign(window=year))
        coverage.append(observed.assign(window=year))
        windows.append({'window': year, 'train_rows': len(train), 'evaluation_rows': len(evaluation),
                        'train_objects': train.vote_id.nunique(), 'evaluation_objects': evaluation.vote_id.nunique(),
                        'train_dates': sorted(train.vote_date.dt.strftime('%Y-%m-%d').unique().tolist()),
                        'evaluation_dates': sorted(evaluation.vote_date.dt.strftime('%Y-%m-%d').unique().tolist()),
                        'history_cutoff': str(train.vote_date.max().date()), 'model_details': details})
    predictions = pd.concat(predictions, ignore_index=True)
    metrics, objects, dates = [], [], []
    for year, group in predictions.groupby('window'):
        a, b, c = demo.report_metrics(group)
        metrics.append(a.assign(window=year))
        objects.append(b.assign(window=year))
        dates.append(c.assign(window=year))
    metrics, objects, dates = (pd.concat(t, ignore_index=True) for t in [metrics, objects, dates])
    gains = paired_gains(metrics, ['window'], 'mae_pp')
    date_gains = paired_gains(dates, ['window', 'vote_date'], 'absolute_error_pp')
    object_gains = paired_gains(objects, ['window', 'vote_id', 'vote_date'], 'absolute_error_pp')
    summary = gains.groupby('model', as_index=False).agg(
        mean_window_mae_pp=('mae_pp', 'mean'), mean_window_gain_pp=('gain_pp', 'mean'),
        min_gain_pp=('gain_pp', 'min'), max_gain_pp=('gain_pp', 'max'),
        positive_windows=('gain_pp', lambda x: int(x.gt(0).sum())), windows=('window', 'nunique'))
    dates_summary = date_gains.groupby('model', as_index=False).agg(
        mean_date_gain_pp=('gain_pp', 'mean'), positive_dates=('gain_pp', lambda x: int(x.gt(0).sum())),
        dates=('vote_date', 'nunique'))
    contrasts = []
    for label, (candidate, reference) in CONTRASTS.items():
        compared = paired_gains(metrics, ['window'], 'mae_pp', reference=reference)
        contrasts.append(compared.loc[compared.model.eq(candidate)].assign(contrast=label, reference=reference))
    contrasts = pd.concat(contrasts, ignore_index=True)
    contrast_summary = contrasts.groupby(['contrast', 'model', 'reference'], as_index=False).agg(
        mean_gain_pp=('gain_pp', 'mean'), min_gain_pp=('gain_pp', 'min'), max_gain_pp=('gain_pp', 'max'),
        positive_windows=('gain_pp', lambda x: int(x.gt(0).sum())), windows=('window', 'nunique'))
    return {'predictions': predictions, 'metrics': metrics, 'by_object': objects, 'by_date': dates,
            'window_gains': gains, 'object_gains': object_gains, 'date_gains': date_gains,
            'summary': summary.merge(dates_summary, on='model', validate='one_to_one'),
            'contrasts': contrasts, 'contrast_summary': contrast_summary,
            'coverage': pd.concat(coverage, ignore_index=True)}, windows


def run(root, output):
    root, output = Path(root), Path(output)
    data, source_manifest, _ = demo.load_inputs(root, last_date=demo.TRAIN_END)
    swissvotes_path = root / source_manifest['sources']['swissvotes']['path']
    swissvotes = pd.read_parquet(swissvotes_path, filters=[('vote_date', '<=', demo.TRAIN_END)],
                                columns=['vote_key', 'vote_date'] + [f'p-{p}' for p in PARTIES.values()])
    data = attach_recommendations(data, swissvotes)
    source = pd.read_parquet(root / source_manifest['sources']['ofs']['path'],
                             filters=[('vote_date', '<=', demo.TRAIN_END)])
    outcomes, _ = clean_outcomes(source)
    tables, windows = evaluate(data, outcomes)
    # Audit the existing corpus; unresolved links do not silently become model inputs.
    links_path = root / 'data/processed/federal_explanations/section_links.parquet'
    text_status = {'status': 'not_evaluated', 'reason': 'No reviewed forecast-time corpus provided'}
    if links_path.exists():
        links = pd.read_parquet(links_path, columns=['match_status'])
        text_status['link_status_counts'] = links.match_status.value_counts(dropna=False).to_dict()
        text_status['links_sha256'] = demo.sha256(links_path)
    manifest = {'mode': 'exploratory_retrospective', 'strict_forecast_ready': False,
                'validation_2021_2022_loaded': False, 'test_evaluated': False,
                'hyperparameter_search': False, 'automatic_selection': False,
                'ridge_alpha': 1., 'latent_dimensions': LATENT_DIMENSIONS,
                'theme_columns': THEMES, 'local_numeric': LOCAL_NUMERIC, 'local_categorical': LOCAL_CATEGORICAL,
                'recommendation_parties': PARTIES, 'recommendation_availability': 'historically_unverified',
                'recommendation_codes_source': 'https://swissvotes.ch/page/dataset/codebook-de.pdf',
                'sources': source_manifest['sources'], 'source_blocks': source_manifest['blocks'],
                'dataset_sha256': demo.sha256(root / 'data/processed/modeling/municipal_structured.parquet'),
                'history_policy': 'Strictly earlier dates including pre-2012; frozen at each training cutoff',
                'windows': windows, 'text_experiment': text_status,
                'implementation_sha256': {p.name: demo.sha256(p) for p in [Path(__file__), Path(demo.__file__),
                                         Path(blocks.__file__), Path(demo.__file__).with_name('regularized_votes.py')]},
                'versions': {'python': platform.python_version(), 'numpy': np.__version__,
                             'pandas': pd.__version__, 'sklearn': sklearn.__version__}}
    output.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        if name == 'predictions':
            table.to_parquet(output / 'predictions.parquet', index=False)
        else:
            table.to_csv(output / f'{name}.csv', index=False)
    (output / 'run_manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    gains = tables['window_gains']
    fig, ax = plt.subplots(figsize=(12, 6))
    for name, group in gains.groupby('model'):
        if name != 'ridge_combined':
            ax.plot(group.window, group.gain_pp, marker='o', label=name)
    ax.axhline(0, color='grey', linewidth=.8)
    ax.set(xlabel='Année évaluée', ylabel='Gain vs Ridge combiné (points de MAE)',
           title='Interactions et profils latents · positif = amélioration', xticks=blocks.EVALUATION_YEARS)
    ax.legend(fontsize=8, bbox_to_anchor=(1, 1))
    fig.tight_layout()
    for ext in ['png', 'svg']:
        fig.savefig(output / f'window_gains.{ext}', dpi=180, bbox_inches='tight')
    plt.close(fig)
    report = f'''# Interactions et profils latents : résultats rétrospectifs internes

Expérience du 1er novembre 2026. Cinq fenêtres internes 2016–2020, entraînement
croissant depuis 2012 ; historique pré-2012 inclus et gelé à chaque coupure.
Neuf modèles, paramètres fixés avant exécution. Aucun réglage sur les résultats
ci-dessous et aucune sélection automatique. Validation 2021–2022 et test
2023–2025 non chargés. Les fenêtres internes étaient déjà explorées.

## Scores et stabilité

MAE en points de pourcentage ; moyenne à poids égal par fenêtre. Gain positif =
réduction d'erreur par rapport au Ridge combiné. Les minima/maxima décrivent
les cinq fenêtres, sans intervalle de confiance. Les gains moyens par date
attribuent le même poids à chaque date, distinct du poids égal par année.

{tables['summary'].to_markdown(index=False, floatfmt='.6f')}

## Comparaisons isolant chaque ajout

Gain = MAE de référence moins MAE du candidat. Une amélioration par rapport au
Ridge combiné n'implique pas que chaque interaction ajoutée est utile : les
contrastes suivants isolent les recommandations, leurs interactions locales et
les facteurs latents.

{tables['contrast_summary'].to_markdown(index=False, floatfmt='.6f')}

## Méthode et limites

Le Ridge de base est reproduit. Alpha = 1 pour tous les Ridge ; les interactions
de thème utilisent une matrice creuse et le solveur lsqr avec tolérance 1e-6.
Boosting reprend les réglages fixes de la démonstration, sans early stopping.
Les consignes nationales de huit partis sont catégorielles ; le produit avec
leur force communale utilise +1 pour oui, −1 pour non et 0 pour une position
neutre définie. Les inconnues restent manquantes ; les dissidences cantonales
ne sont pas modélisées. Voir le protocole pour le traitement de chaque code.

Les deux modèles au niveau objet apprennent sur les objets uniques, à poids
égal. Ils utilisent métadonnées et recommandations pour prédire la moyenne
communale. Le modèle latent ajoute trois axes issus d'une SVD des résultats
d'entraînement centrés par objet. Les cellules absentes sont centrées à zéro,
soit un repli sur la moyenne de leur objet historique. Une commune inconnue
à l'évaluation reçoit la moyenne d'objet prédite. Aucun résultat du nouvel
objet ne sert à identifier ses facteurs ou sa moyenne. Cette moyenne communale
n'est pas la part nationale pondérée par suffrages.

La géographie 2026, l'édition actuelle des sources et les dates historiques de
publication des consignes non prouvées limitent l'expérience au rétrospectif.
Elle ne satisfait pas les critères de prévision stricte V1. Les observations
communales sont dépendantes et les fenêtres partagent leur entraînement.
Les scores nationaux/classifications des études publiées ne sont pas comparables
à ces MAE communales. Aucun effet causal ni gain opérationnel n'est établi.

## Expérience textuelle

{json.dumps(text_status, ensure_ascii=False)}

Aucune brochure n'est jointe arbitrairement à un objet. Une expérience textuelle
requiert d'abord le corpus relu avec correspondances, dates et versions admissibles.

## Reproduction

```bash
python -m scripts.modeling.interaction_experiment
```

Les prédictions et scores par objet/date/fenêtre, les contrastes, la couverture,
les figures et les paramètres/empreintes sont exportés dans ce dossier. Le guide
du dépôt est `docs/project/interaction_experiment.md`.
'''
    (output / 'report.md').write_text(report, encoding='utf-8')
    print(tables['summary'].to_string(index=False))
    return tables, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/generated/interaction_experiment')
    args = parser.parse_args()
    run(ROOT, args.output)


if __name__ == '__main__':
    main()

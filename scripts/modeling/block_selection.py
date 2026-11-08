"""Retrospective Ridge block additions/removals inside 2012–2020 only.

Run with python -m scripts.modeling.block_selection. No automatic feature selection.
"""
from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from threadpoolctl import threadpool_limits

from scripts.common.config import ROOT
from scripts.integration.build_modeling_dataset import clean_outcomes
from scripts.modeling import retrospective_demo as demo

EVALUATION_YEARS = (2016, 2017, 2018, 2019, 2020)
HISTORY = ['history_mean_yes', 'history_n_objects', 'history_missing']


def block_features():
    return {
        'demography': ([c for c in demo.NUMERIC if c.startswith('statpop_')] + ['statpop_missing'], []),
        'parties': ([c for c in demo.NUMERIC if c.startswith('party_share_')] + ['elections_missing'], []),
        'typologies': ([], [c for c in demo.CATEGORICAL if not c.startswith('object_')]),
        'object': ([], [c for c in demo.CATEGORICAL if c.startswith('object_')]),
    }


def feature_sets():
    blocks = block_features()
    full = (demo.NUMERIC + demo.INDICATORS, demo.CATEGORICAL)
    return {
        'history': (HISTORY, []), 'combined': full,
        **{f'add_{name}': (HISTORY + numeric, categorical)
           for name, (numeric, categorical) in blocks.items()},
        **{f'remove_{name}': ([c for c in full[0] if c not in numeric],
                             [c for c in full[1] if c not in categorical])
           for name, (numeric, categorical) in blocks.items()},
    }


def chronological_windows(data, years=EVALUATION_YEARS):
    if data.empty or data.vote_date.isna().any() or not data.vote_date.between('2012-01-01', demo.TRAIN_END).all():
        raise ValueError('Only 2012–2020 training observations are allowed')
    if data[['municipality_id', 'vote_id']].isna().any().any() or data.duplicated(['municipality_id', 'vote_id']).any():
        raise ValueError('Invalid or duplicate observation keys')
    if not data.groupby('vote_id').vote_date.nunique().eq(1).all():
        raise ValueError('An object must belong to one date')
    if not data.yes_share.between(0, 1).all():
        raise ValueError('Invalid target shares')
    if not years or tuple(sorted(set(years))) != tuple(years):
        raise ValueError('Evaluation years must be unique and increasing')
    for year in years:
        if year < 2013 or year > 2020:
            raise ValueError('Evaluation years must be inside 2013–2020')
        train = data.loc[data.vote_date.lt(f'{year}-01-01')].copy()
        evaluation = data.loc[data.vote_date.dt.year.eq(year)].copy()
        if train.empty or evaluation.empty:
            raise ValueError(f'Empty training or evaluation window: {year}')
        yield year, train, evaluation


def fit_window(train, evaluation, outcomes):
    cutoff = train.vote_date.max()
    if cutoff >= evaluation.vote_date.min():
        raise ValueError('Training must precede evaluation dates')
    # Replace every precomputed history column, freezing all held-out dates at the fit cutoff.
    train, evaluation = train.copy(), evaluation.copy()
    for frame in [train, evaluation]:
        history = demo.frozen_history(frame, outcomes, train_end=cutoff)
        frame[history.columns] = history
    x_train, x_evaluation = demo.model_input(train), demo.model_input(evaluation)
    predictions, coverage = [], []
    with threadpool_limits(limits=1):
        for name, (numeric, categorical) in feature_sets().items():
            model = demo.ridge_pipeline(numeric, categorical, 1.0)
            model.fit(x_train, train.yes_share.astype(float))
            raw = model.predict(x_evaluation)
            if not np.isfinite(raw).all():
                raise ValueError(f'Nonfinite predictions: {name}')
            frame = evaluation[['municipality_id', 'vote_id', 'vote_date', 'yes_share']].rename(
                columns={'yes_share': 'target_share'}).copy()
            frame['model'], frame['raw_prediction'] = name, raw
            frame['prediction'] = np.clip(raw, 0, 1)
            frame['clipped'] = raw != frame.prediction
            predictions.append(frame)
            for partition, source in [('train', train), ('evaluation', evaluation)]:
                observed = source[numeric + categorical].notna()
                coverage.append({'model': name, 'partition': partition, 'rows': len(source),
                                 'objects': source.vote_id.nunique(), 'dates': source.vote_date.nunique(),
                                 'observed_cell_share': observed.to_numpy().mean(),
                                 'all_missing_features': json.dumps(observed.columns[~observed.any()].tolist())})
    return pd.concat(predictions, ignore_index=True), pd.DataFrame(coverage)


def paired_gains(table, keys, value):
    """Positive gain always means the block helped; compare identical units."""
    records = []
    for operation, reference in [('add', 'history'), ('remove', 'combined')]:
        baseline = table.loc[table.model.eq(reference), keys + [value]]
        for block in block_features():
            candidate = table.loc[table.model.eq(f'{operation}_{block}'), keys + [value]]
            paired = candidate.merge(baseline, on=keys, suffixes=('_candidate', '_reference'),
                                     validate='one_to_one', how='outer', indicator=True)
            if not paired['_merge'].eq('both').all():
                raise ValueError('Comparisons must use identical evaluation units')
            sign = -1 if operation == 'add' else 1
            paired['gain_pp'] = sign * (paired[f'{value}_candidate'] - paired[f'{value}_reference'])
            paired['operation'], paired['block'] = operation, block
            records.append(paired.drop(columns='_merge'))
    return pd.concat(records, ignore_index=True)


def evaluate(data, outcomes, years=EVALUATION_YEARS):
    predictions, coverage, windows = [], [], []
    for year, train, evaluation in chronological_windows(data, years):
        print(f'Window {year}: {train.vote_id.nunique()} training objects, '
              f'{evaluation.vote_id.nunique()} evaluation objects', flush=True)
        predicted, observed = fit_window(train, evaluation, outcomes)
        predictions.append(predicted.assign(window=year))
        coverage.append(observed.assign(window=year))
        windows.append({'window': year, 'train_rows': len(train), 'train_objects': train.vote_id.nunique(),
                        'train_dates': sorted(train.vote_date.dt.strftime('%Y-%m-%d').unique().tolist()),
                        'evaluation_rows': len(evaluation), 'evaluation_objects': evaluation.vote_id.nunique(),
                        'evaluation_dates': sorted(evaluation.vote_date.dt.strftime('%Y-%m-%d').unique().tolist()),
                        'history_cutoff': str(train.vote_date.max().date())})
    predictions = pd.concat(predictions, ignore_index=True)
    metrics, objects, dates = [], [], []
    for year, group in predictions.groupby('window', sort=True):
        score, obj, date = demo.report_metrics(group)
        metrics.append(score.assign(window=year))
        objects.append(obj.assign(window=year))
        dates.append(date.assign(window=year))
    metrics, objects, dates = (pd.concat(tables, ignore_index=True) for tables in [metrics, objects, dates])
    gains = paired_gains(metrics, ['window'], 'mae_pp')
    date_gains = paired_gains(dates, ['window', 'vote_date'], 'absolute_error_pp')
    object_gains = paired_gains(objects, ['window', 'vote_id', 'vote_date'], 'absolute_error_pp')
    summary = gains.groupby(['operation', 'block'], as_index=False).agg(
        mean_window_gain_pp=('gain_pp', 'mean'), min_window_gain_pp=('gain_pp', 'min'),
        max_window_gain_pp=('gain_pp', 'max'), positive_windows=('gain_pp', lambda s: int(s.gt(0).sum())),
        windows=('window', 'nunique'))
    by_date = date_gains.groupby(['operation', 'block'], as_index=False).agg(
        mean_date_gain_pp=('gain_pp', 'mean'), positive_dates=('gain_pp', lambda s: int(s.gt(0).sum())),
        dates=('vote_date', 'nunique'))
    return {'predictions': predictions, 'coverage': pd.concat(coverage, ignore_index=True),
            'metrics': metrics, 'by_object': objects, 'by_date': dates, 'window_gains': gains,
            'date_gains': date_gains, 'object_gains': object_gains,
            'summary': summary.merge(by_date, on=['operation', 'block'], validate='one_to_one')}, windows


def plot_gains(gains, output):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
    for ax, operation, title in zip(axes, ['add', 'remove'], ['Ajout à l’historique', 'Retrait du combiné']):
        for block, group in gains.loc[gains.operation.eq(operation)].groupby('block'):
            ax.plot(group.window, group.gain_pp, marker='o', label=block)
        ax.axhline(0, color='grey', linewidth=.8)
        ax.set(title=title, xlabel='Année évaluée', xticks=sorted(gains.window.unique()))
    axes[0].set_ylabel('Gain attribué au bloc (points de MAE)\nPositif = bloc utile')
    axes[1].legend()
    fig.suptitle('Ridge α = 1 · fenêtres internes 2016–2020 · analyse rétrospective')
    fig.tight_layout()
    for extension in ['png', 'svg']:
        fig.savefig(output / f'block_gains.{extension}', dpi=180, bbox_inches='tight')
    plt.close(fig)


def run(root, output):
    root, output = Path(root), Path(output)
    data, source_manifest, _ = demo.load_inputs(root, last_date=demo.TRAIN_END)
    # Read the pre-2012 history pool, never validation/test outcomes.
    source = pd.read_parquet(root / source_manifest['sources']['ofs']['path'],
                             filters=[('vote_date', '<=', demo.TRAIN_END)])
    outcomes, exclusions = clean_outcomes(source)
    tables, windows = evaluate(data, outcomes)
    output.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        if name == 'predictions':
            table.to_parquet(output / 'predictions.parquet', index=False)
        else:
            table.to_csv(output / f'{name}.csv', index=False)
    plot_gains(tables['window_gains'], output)
    manifest = {
        'mode': 'exploratory_retrospective', 'strict_forecast_ready': False,
        'validation_2021_2022_loaded': False, 'test_evaluated': False,
        'evaluation_years': EVALUATION_YEARS, 'windows': windows, 'ridge_alpha': 1.0,
        'hyperparameter_search': False, 'automatic_feature_selection': False,
        'feature_sets': feature_sets(), 'sources': source_manifest['sources'],
        'source_blocks': source_manifest['blocks'], 'outcome_exclusions': exclusions,
        'history_policy': 'Strictly earlier dates including pre-2012; frozen at each training cutoff',
        'gain_policy': 'add: history MAE minus candidate; remove: candidate MAE minus combined',
        'aggregate_policy': 'Equal window means; equal date means also reported; no independent-row CI',
        'dataset_sha256': demo.sha256(root / 'data/processed/modeling/municipal_structured.parquet'),
        'implementation_sha256': {p.name: demo.sha256(p) for p in [Path(__file__), Path(demo.__file__),
                                 Path(demo.__file__).with_name('regularized_votes.py')]},
        'versions': {'python': platform.python_version(), 'pandas': pd.__version__,
                     'numpy': np.__version__, 'sklearn': sklearn.__version__},
        'limitations': ['Retrospective 2026 geography and unverified historical source vintages',
                        'Few dates and objects; dependent municipal observations',
                        'Exploratory comparisons; no causal or operational forecast claim',
                        'Earlier training periods become eligible in later expanding windows'],
    }
    (output / 'run_manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    summary = tables['summary']
    text = f'''# Sélection par blocs : expérience rétrospective interne

Cinq fenêtres annuelles fixées avant exécution : 2016, 2017, 2018, 2019, 2020.
Entraînement croissant depuis 2012, arrêté avant chaque année évaluée.
Historique antérieur à 2012 inclus, gelé à la dernière date d'entraînement.
Ridge alpha = 1 ; chaque configuration réajuste son prétraitement et son modèle.
Même population et mêmes clés pour toutes les comparaisons, prédictions bornées à [0, 1].
Les résultats 2021–2022 et le test 2023–2025 ne sont pas chargés.

## Gains mesurés

Un gain positif signifie que le bloc est utile : historique − ajout pour `add`,
retrait − combiné pour `remove`. Les moyennes par fenêtre donnent le même poids
à chaque année ; les moyennes par date donnent le même poids à chaque date.
Les minima/maxima décrivent la variation entre fenêtres, sans intervalle de confiance.

{summary.to_markdown(index=False, floatfmt='.6f')}

## Population par fenêtre

{pd.DataFrame([{k: v for k, v in w.items() if k not in ['train_dates', 'evaluation_dates']} | {'train_dates': len(w['train_dates']), 'evaluation_dates': len(w['evaluation_dates'])} for w in windows]).to_markdown(index=False)}

## Portée et suite

Ces comparaisons ne sélectionnent automatiquement aucune variable. Interpréter
ensemble l'ajout et le retrait : un bloc redondant peut aider seul sans aider le
combiné. Les sorties détaillent les erreurs et gains par objet et date, ainsi
que la couverture et les colonnes entièrement manquantes dans chaque ajustement.
La géographie 2026 et les versions historiques des sources non prouvées limitent
l'expérience à l'exploration rétrospective ; la V1 stricte reste inchangée.
Les nombreuses communes ne sont pas autant d'objets indépendants. Les fenêtres
partagent des données d'entraînement et ne sont pas des réplications indépendantes.
Aucun effet causal ni score final de prévision n'est établi.

Les comparaisons concernent le Ridge alpha = 1, pas les performances possibles
d'autres modèles ou réglages. Aucune permutation n'est exécutée ici : il faut
d'abord définir ses échanges admissibles au niveau objet/commune et leurs cutoffs.
Les hypothèses et empreintes figurent dans `run_manifest.json` ; les tableaux,
prédictions et graphiques sont régénérés avec :

```bash
python -m scripts.modeling.block_selection
```
'''
    (output / 'report.md').write_text(text, encoding='utf-8')
    print(summary.to_string(index=False))
    return tables, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/generated/block_selection')
    args = parser.parse_args()
    run(ROOT, args.output)


if __name__ == '__main__':
    main()

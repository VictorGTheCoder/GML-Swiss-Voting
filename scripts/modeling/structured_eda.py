"""Train-only EDA and fixed Ridge block comparisons for the retrospective demo.

Uses the demo's audited loader; no test outcomes are loaded or scored.
"""
from __future__ import annotations

import json
import platform
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from threadpoolctl import threadpool_limits

from scripts.modeling import retrospective_demo as demo


def feature_sets():
    """Keep the published baseline, then use identical complete history in every block fit."""
    published = ['history_mean_yes', 'history_missing']
    history = published + ['history_n_objects']
    groups = {
        'demography': ([c for c in demo.NUMERIC if c.startswith('statpop_')] + ['statpop_missing'], []),
        'parties': ([c for c in demo.NUMERIC if c.startswith('party_share_')] + ['elections_missing'], []),
        'typologies': ([], [c for c in demo.CATEGORICAL if not c.startswith('object_')]),
        'object': ([], [c for c in demo.CATEGORICAL if c.startswith('object_')]),
    }
    return {
        'ridge_history': (published, []),
        'ridge_history_count': (history, []),
        **{f'ridge_{name}': (history + numeric, categorical)
           for name, (numeric, categorical) in groups.items()},
        'ridge_combined': (demo.NUMERIC + demo.INDICATORS, demo.CATEGORICAL),
    }


def training_inventory(train):
    """Describe declared predictors only; targets and identifiers never enter correlations."""
    features = demo.NUMERIC + demo.INDICATORS + demo.CATEGORICAL
    inventory = pd.DataFrame({
        'missing_share': train[features].isna().mean(),
        'distinct_nonmissing': train[features].nunique(),
        'role': ['categorical' if c in demo.CATEGORICAL else 'numeric' for c in features],
    }).rename_axis('feature')
    inventory['dominant_nonmissing_share'] = [
        train[c].value_counts(normalize=True).max() for c in features]
    inventory['all_missing'] = inventory.missing_share.eq(1)
    inventory['constant_nonmissing'] = inventory.distinct_nonmissing.le(1)
    return inventory


def source_coverage(data):
    """Report observed source cells, independently of imputation and evaluation scores."""
    records = []
    for partition, frame in data.groupby('partition', sort=True):
        for name, (numeric, categorical) in feature_sets().items():
            # Explicit flags are metadata, not evidence of an observed source value.
            features = [c for c in numeric + categorical if c not in demo.INDICATORS]
            observed = frame[features].notna()
            records.append({'partition': partition, 'model': name, 'rows': len(frame),
                            'objects': frame.vote_id.nunique(), 'dates': frame.vote_date.nunique(),
                            'observed_cell_share': observed.to_numpy().mean(),
                            'all_features_observed_share': observed.all(axis=1).mean(),
                            'per_feature_observed_share': json.dumps(observed.mean().to_dict(), sort_keys=True)})
    return pd.DataFrame(records)


def fit_comparisons(train, validation):
    """Fit on training only; score every configuration on identical validation keys."""
    if not train.vote_date.le(demo.TRAIN_END).all():
        raise ValueError('Fitting requires training dates only')
    if not (validation.vote_date.gt(demo.TRAIN_END) & validation.vote_date.le(demo.VALIDATION_END)).all():
        raise ValueError('Scoring requires 2021–2022 validation dates only')
    keys = ['municipality_id', 'vote_id', 'vote_date']
    if train.duplicated(keys).any() or validation.duplicated(keys).any():
        raise ValueError('Duplicate observation keys')
    x_train, x_validation = demo.model_input(train), demo.model_input(validation)
    fits, predictions = {}, []
    with threadpool_limits(limits=1):
        for name, (numeric, categorical) in feature_sets().items():
            model = demo.ridge_pipeline(numeric, categorical, 1.0)
            model.fit(x_train, train.yes_share.astype(float))
            raw = model.predict(x_validation)
            if not np.isfinite(raw).all():
                raise ValueError(f'Nonfinite predictions: {name}')
            frame = validation[keys + ['yes_share']].rename(columns={'yes_share': 'target_share'}).copy()
            frame['model'], frame['raw_prediction'] = name, raw
            frame['prediction'] = np.clip(raw, 0, 1)
            frame['clipped'] = raw != frame.prediction
            fits[name] = model
            predictions.append(frame)
    predictions = pd.concat(predictions, ignore_index=True)
    scores, objects, dates = demo.report_metrics(predictions)
    reference = scores.set_index('model').loc['ridge_history_count', 'mae_pp']
    scores['delta_vs_history_count_pp'] = scores.mae_pp - reference
    for table in [objects, dates]:
        pairing = ['vote_id', 'vote_date'] if 'vote_id' in table else ['vote_date']
        baseline = table.loc[table.model.eq('ridge_history_count'), pairing + ['absolute_error_pp']]
        paired = table.merge(baseline, on=pairing, suffixes=('', '_reference'), validate='many_to_one')
        paired['delta_vs_history_count_pp'] = paired.absolute_error_pp - paired.absolute_error_pp_reference
        if 'vote_id' in table:
            objects = paired
        else:
            dates = paired
    return fits, predictions, scores, objects, dates


def coefficient_table(model):
    """Preserve transformed feature names and distinguish coefficient scales."""
    names = model.named_steps['prepare'].get_feature_names_out()
    values = model.named_steps['ridge'].coef_
    table = pd.DataFrame({'feature': names, 'coefficient_pp': values * 100})
    table['representation'] = np.select(
        [table.feature.str.startswith('numeric__'), table.feature.str.startswith('categorical__')],
        ['numeric: one training SD after imputation', 'categorical: one-hot level'],
        default='missingness: binary flag')
    return table


def save_figure(fig, output, name):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    fig.savefig(output / f'{name}.png', dpi=180, bbox_inches='tight')
    fig.savefig(output / f'{name}.svg', bbox_inches='tight')
    return fig


def quality_figures(train, output):
    """All descriptive plots take the training frame explicitly."""
    inventory = training_inventory(train)
    fig, ax = plt.subplots(figsize=(9, 9))
    (inventory.missing_share.sort_values() * 100).plot.barh(ax=ax)
    ax.set(xlabel='Valeurs manquantes (%) · entraînement', title='Qualité des variables')
    fig.tight_layout()
    yield save_figure(fig, output, 'training_missingness')

    fig, axes = plt.subplots(5, 4, figsize=(15, 15))
    for ax, column in zip(axes.flat, demo.NUMERIC):
        observed = train[column].dropna().astype(float)
        ax.hist(observed, bins=35)
        ax.set_title(column, fontsize=9)
        ax.set_ylabel('Lignes communales')
        if observed.empty:
            ax.text(.5, .5, 'Entièrement manquante', ha='center', transform=ax.transAxes)
    for ax in list(axes.flat)[len(demo.NUMERIC):]:
        ax.set_visible(False)
    fig.suptitle('Distributions · entraînement · valeurs observées')
    fig.tight_layout()
    yield save_figure(fig, output, 'training_distributions')

    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for ax, column in zip(axes.flat, demo.CATEGORICAL):
        # Object-level codes repeat across municipalities: count each object once.
        frame = train.drop_duplicates('vote_id') if column.startswith('object_') else train
        counts = frame[column].astype('string').fillna('manquant').value_counts().sort_index()
        counts.plot.bar(ax=ax)
        ax.set(title=column, ylabel='Objets' if column.startswith('object_') else 'Lignes communales')
    fig.suptitle('Modalités nominales · entraînement')
    fig.tight_layout()
    yield save_figure(fig, output, 'training_categories')

    corr = train[demo.NUMERIC].corr(method='spearman')
    fig, ax = plt.subplots(figsize=(12, 10))
    cmap = plt.get_cmap('coolwarm').copy()
    cmap.set_bad('lightgrey')
    image = ax.imshow(corr, vmin=-1, vmax=1, cmap=cmap)
    ax.set_xticks(range(len(corr)), corr.columns, rotation=90, fontsize=8)
    ax.set_yticks(range(len(corr)), corr.columns, fontsize=8)
    ax.set_title('Spearman entre variables numériques · entraînement\nGris : corrélation indéfinie')
    fig.colorbar(image, ax=ax)
    fig.tight_layout()
    yield save_figure(fig, output, 'training_correlations')


def target_figures(train, output):
    # Fixed sample for legibility only; full training data remain in the tables.
    sample = train.sample(n=min(4000, len(train)), random_state=42)
    columns = ['history_mean_yes', 'statpop_share_foreign', 'statpop_mean_age', 'party_share_udc']
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    for ax, column in zip(axes.flat, columns):
        ax.scatter(sample[column].astype(float), sample.yes_share * 100, s=4, alpha=.12)
        ax.set(xlabel=column, ylabel='Part de oui (%)')
    fig.suptitle('Associations marginales · entraînement · échantillon fixe de lignes')
    fig.tight_layout()
    yield save_figure(fig, output, 'training_target_scatter')

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, column in zip(axes, ['language_region', 'urban_rural']):
        groups = list(train.groupby(column, dropna=False, sort=True))
        ax.boxplot([g.yes_share.to_numpy() * 100 for _, g in groups],
                   tick_labels=[str(k) for k, _ in groups], showfliers=False)
        ax.set(xlabel=f'{column} (code nominal)', ylabel='Part de oui (%)')
    fig.suptitle('Entraînement · boîtes : médiane, quartiles et moustaches 1,5 IQR\n'
                 'Extrêmes masqués sur la figure uniquement ; observations dépendantes')
    fig.tight_layout()
    yield save_figure(fig, output, 'training_target_typologies')

    object_columns = [c for c in demo.CATEGORICAL if c.startswith('object_')]
    objects = train.groupby('vote_id', as_index=False).agg(
        yes_share=('yes_share', 'mean'), **{c: (c, 'first') for c in object_columns})
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    for ax, column in zip(axes.flat, object_columns):
        groups = list(objects.groupby(column, dropna=False, sort=True))
        for position, (_, group) in enumerate(groups):
            ax.scatter(np.full(len(group), position), group.yes_share * 100, s=15, alpha=.5)
        ax.set_xticks(range(len(groups)), [str(k) for k, _ in groups], rotation=45)
        ax.set(xlabel=f'{column} (code nominal)', ylabel='Moyenne communale du oui (%)')
    fig.suptitle('Entraînement · une observation par objet, sans pondération démographique')
    fig.tight_layout()
    yield save_figure(fig, output, 'training_target_objects')


def model_figures(coefficients, scores, objects, dates, output):
    fig, axes = plt.subplots(1, 3, figsize=(18, 7))
    for ax, (representation, group) in zip(axes, coefficients.groupby('representation', sort=True)):
        chosen = group.loc[group.coefficient_pp.abs().nlargest(12).index].sort_values('coefficient_pp')
        ax.barh(chosen.feature, chosen.coefficient_pp, color=np.where(chosen.coefficient_pp.ge(0), 'teal', 'coral'))
        ax.axvline(0, color='black', linewidth=.7)
        ax.set(title=representation, xlabel='Coefficient (points de oui)')
        ax.tick_params(axis='y', labelsize=7)
    fig.suptitle('Ridge combiné · ajustement sur entraînement · coefficients avant clipping\n'
                 'Échelles distinctes : ne pas classer ensemble les trois représentations')
    fig.tight_layout()
    yield save_figure(fig, output, 'ridge_coefficients')

    ordered = scores.sort_values('mae_pp')
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.barh(ordered.model, ordered.mae_pp)
    ax.set(xlabel='MAE communale (points) · plus faible = meilleur',
           title='Validation réutilisée 2021–2022 · comparaisons exploratoires')
    fig.tight_layout()
    yield save_figure(fig, output, 'validation_block_mae')

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    for ax, table, key in zip(axes, [objects, dates], ['vote_id', 'vote_date']):
        paired = table.loc[table.model.eq('ridge_combined')].sort_values('delta_vs_history_count_pp')
        labels = paired[key].astype(str)
        ax.barh(labels, paired.delta_vs_history_count_pp)
        ax.axvline(0, color='black', linewidth=.7)
        ax.set(xlabel='Δ MAE combiné − historique complet (points)', ylabel=key)
    fig.suptitle('Validation réutilisée · valeurs négatives = gain\n'
                 'Chaque objet/date contribue une fois ; aucun intervalle indépendant')
    fig.tight_layout()
    yield save_figure(fig, output, 'validation_paired_deltas')


def export_results(root, output, source_manifest, inventory, coverage, coefficients,
                   predictions, scores, objects, dates):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for name, table in {'training_inventory': inventory.reset_index(), 'coverage': coverage,
                        'ridge_coefficients': coefficients, 'validation_metrics': scores,
                        'validation_by_object': objects, 'validation_by_date': dates}.items():
        table.to_csv(output / f'{name}.csv', index=False)
    predictions.to_parquet(output / 'validation_predictions.parquet', index=False)
    manifest = {
        'mode': 'exploratory_retrospective', 'test_evaluated': False,
        'eda_partition': 'train 2012–2020', 'validation': '2021–2022, previously exposed',
        'train_end': str(demo.TRAIN_END.date()), 'validation_end': str(demo.VALIDATION_END.date()),
        'ridge_alpha': 1.0, 'hyperparameter_search': False, 'feature_selection': False,
        'permutation_importance': 'deferred', 'reference': 'ridge_history_count',
        'history_policy': 'strictly earlier dates including pre-2012, frozen at end 2020',
        'feature_sets': feature_sets(), 'sources': source_manifest['sources'],
        'dataset_sha256': demo.sha256(root / 'data/processed/modeling/municipal_structured.parquet'),
        'runner_sha256': demo.sha256(Path(__file__)),
        'demo_loader_sha256': demo.sha256(Path(demo.__file__)),
        'ridge_implementation_sha256': demo.sha256(Path(demo.__file__).with_name('regularized_votes.py')),
        'notebook_sha256': demo.sha256(root / 'notebooks/modeling/02_structured_eda.ipynb'),
        'versions': {'python': platform.python_version(), 'pandas': pd.__version__,
                     'numpy': np.__version__, 'sklearn': sklearn.__version__},
        'limitations': ['retrospective geography and source vintages', 'validation reused',
                        'dependent municipal observations', 'no causal or operational forecast claim'],
    }
    (output / 'run_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest

"""Compare recent and extended training with identical population features and validation."""
from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder
from threadpoolctl import threadpool_limits

from scripts.common.config import ROOT
from scripts.espop import population_history as population_source
from scripts.integration.build_modeling_dataset import OBJECT_FIELDS, TYPOLOGIES, asof_join, clean_outcomes
from scripts.integration.prepare_join import prepare_join
from scripts.modeling import retrospective_demo as demo

HISTORY = ['history_mean_yes', 'history_n_objects', 'history_missing']
POPULATION = ['population_total', 'population_share_foreign']
CATEGORICAL = TYPOLOGIES + list(OBJECT_FIELDS.values())
STARTS = {'recent': pd.Timestamp('2012-01-01'), 'extended': pd.Timestamp('1981-01-01')}


def feature_sets():
    return {'history': (HISTORY, []), 'context': (HISTORY, CATEGORICAL),
            'population': (HISTORY + POPULATION, CATEGORICAL)}


def build_table(ofs, swissvotes, typologies, population):
    """Keep population-release selection separate from its observed year and validity."""
    if ofs.vote_date.gt(demo.VALIDATION_END).any():
        raise ValueError('Only outcomes through 2022 may enter this experiment')
    prepare_join(ofs, swissvotes)
    clean, exclusions = clean_outcomes(ofs)
    history_pool = clean.loc[clean.vote_date.le(demo.TRAIN_END)]
    table = clean.loc[clean.vote_date.ge(STARTS['extended']),
                      ['municipality_id', 'vote_id', 'vote_key', 'vote_date', 'canton', 'yes_share']].copy()
    if table.empty:
        raise ValueError('No historical observations')
    history = demo.frozen_history(table, history_pool)
    table[history.columns] = history
    table['feature_cutoff'] = table.vote_date - pd.Timedelta(days=1)
    keep = ['municipality_id', 'year', 'population_total', 'population_share_foreign',
            'population_source', 'population_selection_from', 'population_reference_date',
            'population_valid', 'population_missing_reason']
    table = asof_join(table, population[keep].rename(columns={'year': 'population_year'}),
                       'population_selection_from')
    table = table.merge(typologies[['municipality_id'] + TYPOLOGIES], on='municipality_id',
                        how='left', validate='many_to_one')
    metadata = swissvotes[['vote_key'] + list(OBJECT_FIELDS)].rename(columns=OBJECT_FIELDS)
    table = table.merge(metadata, on='vote_key', how='left', validate='many_to_one')
    table['has_valid_population'] = table.population_valid.eq(True) & table[POPULATION].notna().all(axis=1)
    table['exclusion_reason'] = np.where(table.population_selection_from.isna(),
                                         'no_prior_population_release_or_unmatched_geography',
                                         table.population_missing_reason.fillna('invalid_population'))
    table.loc[table.has_valid_population, 'exclusion_reason'] = ''
    table['year'] = table.vote_date.dt.year
    coverage = table.groupby('year', as_index=False).agg(
        candidate_rows=('vote_id', 'size'), objects=('vote_id', 'nunique'), dates=('vote_date', 'nunique'),
        valid_population_rows=('has_valid_population', 'sum'))
    coverage['excluded_rows'] = coverage.candidate_rows - coverage.valid_population_rows
    rejected = table.loc[~table.has_valid_population,
                         ['municipality_id', 'vote_id', 'vote_date', 'population_year', 'exclusion_reason']]
    table = table.loc[table.has_valid_population].copy().sort_values(
        ['vote_date', 'vote_id', 'municipality_id']).reset_index(drop=True)
    table['geography_id'] = 'retrospective_fixed_2026-01-01'
    table['strict_forecast_ready'] = False
    table['partition'] = np.where(table.vote_date.le(demo.TRAIN_END), 'train', 'validation')
    if table.duplicated(['municipality_id', 'vote_id']).any():
        raise ValueError('Duplicate modeling keys')
    if not (table.population_selection_from.le(table.feature_cutoff)).all():
        raise ValueError('Future population reference selected')
    if (table.history_last_vote_date.notna() &
            (table.history_last_vote_date.ge(table.vote_date) | table.history_last_vote_date.gt(demo.TRAIN_END))).any():
        raise ValueError('Same-date or held-out target entered history')
    return table, coverage, rejected, exclusions


def input_frame(frame):
    x = frame[HISTORY + POPULATION + CATEGORICAL].copy()
    for c in HISTORY + POPULATION:
        x[c] = x[c].astype(float)
    for c in CATEGORICAL:
        x[c] = x[c].astype(object).where(x[c].notna(), np.nan)
    return x


def boosting_pipeline(train, numeric, categorical):
    numeric = [c for c in numeric if not train[c].isna().all()]
    categorical = [c for c in categorical if not train[c].isna().all()]
    settings = {'loss': 'squared_error', 'learning_rate': .1, 'max_iter': 100, 'max_leaf_nodes': 31,
                'min_samples_leaf': 20, 'l2_regularization': 0., 'early_stopping': False, 'random_state': 42}
    transformers = [('numeric', 'passthrough', numeric)]
    if categorical:
        transformers.append(('categorical', OrdinalEncoder(handle_unknown='use_encoded_value',
                            unknown_value=np.nan, encoded_missing_value=np.nan), categorical))
    prepare = ColumnTransformer(transformers, sparse_threshold=0)
    return Pipeline([('prepare', prepare), ('model', HistGradientBoostingRegressor(
        **settings, categorical_features=[False] * len(numeric) + [True] * len(categorical)))])


def paired_contrast(table, keys, value, candidate, reference, name):
    if not keys:
        table = table.assign(_unit=0)
        keys = ['_unit']
    base = table.loc[table.model.eq(reference), keys + [value]]
    compared = table.loc[table.model.eq(candidate), keys + [value]].merge(
        base, on=keys, how='outer', suffixes=('_candidate', '_reference'), validate='one_to_one', indicator=True)
    if compared.empty or not compared['_merge'].eq('both').all():
        raise ValueError('Comparisons require identical evaluation units')
    compared['gain_pp'] = compared[f'{value}_reference'] - compared[f'{value}_candidate']
    return compared.drop(columns=['_merge', '_unit'], errors='ignore').assign(
        contrast=name, candidate=candidate, reference=reference)


def evaluate(table, model_output=None):
    if table.empty or not table.vote_date.between('1981-01-01', demo.VALIDATION_END).all():
        raise ValueError('Expected retrospective dates 1981–2022')
    if not table.has_valid_population.all():
        raise ValueError('All models must share the population-covered sample')
    validation = table.loc[table.vote_date.gt(demo.TRAIN_END)]
    if validation.empty:
        raise ValueError('No validation observations')
    xe = input_frame(validation)
    predictions, partitions, preprocessing = [], [], []
    with threadpool_limits(limits=1):
        for regime, start in STARTS.items():
            train = table.loc[table.vote_date.ge(start) & table.vote_date.le(demo.TRAIN_END)]
            if train.empty:
                raise ValueError(f'No training observations for {regime}')
            xt = input_frame(train)
            partitions.append({'regime': regime, 'rows': len(train), 'objects': train.vote_id.nunique(),
                               'dates': train.vote_date.nunique(), 'municipalities': train.municipality_id.nunique(),
                               'first_date': str(train.vote_date.min().date()), 'last_date': str(train.vote_date.max().date())})
            for config, (numeric, categorical) in feature_sets().items():
                for family in ['ridge', 'boosting']:
                    name = f'{family}_{config}_{regime}'
                    print(f'Fit {name}: {len(train):,} rows / {train.vote_id.nunique()} objects', flush=True)
                    model = (demo.ridge_pipeline(numeric, categorical, 1.) if family == 'ridge'
                             else boosting_pipeline(xt, numeric, categorical))
                    model.fit(xt, train.yes_share.astype(float))
                    raw = model.predict(xe)
                    if not np.isfinite(raw).all():
                        raise ValueError(f'Nonfinite predictions: {name}')
                    frame = validation[['municipality_id', 'vote_id', 'vote_date', 'yes_share']].rename(
                        columns={'yes_share': 'target_share'}).copy()
                    frame['model'], frame['raw_prediction'] = name, raw
                    frame['prediction'] = np.clip(raw, 0, 1)
                    frame['clipped'] = raw != frame.prediction
                    predictions.append(frame)
                    preprocessing.append({'model': name, 'family': family, 'regime': regime, 'config': config,
                                          'numeric': numeric, 'categorical': categorical,
                                          'missing_training_features': xt[numeric + categorical].columns[
                                              xt[numeric + categorical].isna().all()].tolist()})
                    if model_output is not None:
                        joblib.dump(model, Path(model_output) / f'{name}.joblib')
    predictions = pd.concat(predictions, ignore_index=True)
    scores, objects, dates = demo.report_metrics(predictions)
    definitions = []
    for family in ['ridge', 'boosting']:
        for config in feature_sets():
            definitions.append((f'{family}_{config}_extended', f'{family}_{config}_recent',
                                f'longer_history__{family}_{config}'))
        for regime in STARTS:
            definitions.append((f'{family}_population_{regime}', f'{family}_context_{regime}',
                                f'population_block__{family}_{regime}'))
    contrasts = {}
    for name, source, keys, value in [('contrasts', scores, [], 'mae_pp'),
                                      ('object_contrasts', objects, ['vote_id', 'vote_date'], 'absolute_error_pp'),
                                      ('date_contrasts', dates, ['vote_date'], 'absolute_error_pp')]:
        contrasts[name] = pd.concat([paired_contrast(source, keys, value, a, b, label)
                                    for a, b, label in definitions], ignore_index=True)
    date_summary = contrasts['date_contrasts'].groupby('contrast', as_index=False).agg(
        mean_date_gain_pp=('gain_pp', 'mean'), positive_dates=('gain_pp', lambda s: int(s.gt(0).sum())),
        dates=('vote_date', 'nunique'))
    contrasts['contrasts'] = contrasts['contrasts'].merge(date_summary, on='contrast', validate='one_to_one')
    return {'predictions': predictions, 'metrics': scores, 'by_object': objects, 'by_date': dates,
            'partitions': pd.DataFrame(partitions), **contrasts}, preprocessing


def run(root=ROOT, population_dir=population_source.DEFAULT_OUTPUT,
        output=ROOT / 'reports/generated/population_history_experiment'):
    root, population_dir, output = map(Path, [root, population_dir, output])
    source_manifest = json.loads((root / 'data/processed/modeling/manifest.json').read_text())
    for source in source_manifest['sources'].values():
        if demo.sha256(root / source['path']) != source['sha256']:
            raise ValueError(f'Changed source: {source["path"]}')
    population_manifest = json.loads((population_dir / 'manifest.json').read_text())
    population_path = population_dir / 'annual_population.parquet'
    if demo.sha256(population_path) != population_manifest['annual_population_sha256']:
        raise ValueError('Population preparation fingerprint mismatch')
    if demo.sha256(root / source_manifest['sources']['statpop']['path']) != population_manifest['statpop_sha256']:
        raise ValueError('STATPOP differs between the population preparation and modeling manifest')
    ofs = pd.read_parquet(root / source_manifest['sources']['ofs']['path'],
                          filters=[('vote_date', '<=', demo.VALIDATION_END)])
    swiss = pd.read_parquet(root / source_manifest['sources']['swissvotes']['path'],
                            filters=[('vote_date', '<=', demo.VALIDATION_END)])
    typologies = pd.read_parquet(root / source_manifest['sources']['typologies']['path'])
    population = pd.read_parquet(population_path)
    table, coverage, rejected, exclusions = build_table(ofs, swiss, typologies, population)
    output.mkdir(parents=True, exist_ok=True)
    table.to_parquet(population_dir / 'municipal_population.parquet', index=False)
    tables, preprocessing = evaluate(table, model_output=output)
    tables['coverage_by_year'], tables['population_exclusions'] = coverage, rejected
    for name, frame in tables.items():
        if name == 'predictions':
            frame.to_parquet(output / 'predictions.parquet', index=False)
        else:
            frame.to_csv(output / f'{name}.csv', index=False)
    validation = table.loc[table.partition.eq('validation')]
    previous_keys = pd.read_parquet(root / 'data/processed/modeling/municipal_structured.parquet',
                                    filters=[('vote_date', '>', demo.TRAIN_END), ('vote_date', '<=', demo.VALIDATION_END)],
                                    columns=['municipality_id', 'vote_id'])
    current_keys = set(zip(validation.municipality_id, validation.vote_id))
    published_keys = set(zip(previous_keys.municipality_id, previous_keys.vote_id))
    manifest = {'mode': 'exploratory_retrospective', 'strict_forecast_ready': False,
                'validation_previously_exposed': True, 'test_evaluated': False,
                'train_end': str(demo.TRAIN_END.date()), 'validation_end': str(demo.VALIDATION_END.date()),
                'sources': source_manifest['sources'], 'population_preparation': population_manifest,
                'source_exclusions': exclusions, 'feature_sets': feature_sets(), 'model_preprocessing': preprocessing,
                'history_policy': 'Strictly earlier dates including pre-1981; frozen at end 2020 in validation, same pool in both regimes',
                'ridge_alpha': 1., 'hyperparameter_search': False, 'automatic_selection': False,
                'row_policy': 'All twelve models use the same population-covered validation rows',
                'validation_rows': len(validation), 'validation_objects': validation.vote_id.nunique(),
                'validation_dates': validation.vote_date.nunique(),
                'published_validation_keys_identical': current_keys == published_keys,
                'published_validation_keys_missing': len(published_keys - current_keys),
                'additional_validation_keys': len(current_keys - published_keys),
                'dataset_sha256': demo.sha256(population_dir / 'municipal_population.parquet'),
                'implementation_sha256': {p.name: demo.sha256(p) for p in [Path(__file__), Path(demo.__file__),
                                         Path(population_source.__file__), root / 'scripts/espop/audit_reuse.py',
                                         root / 'scripts/modeling/regularized_votes.py']},
                'versions': {'python': platform.python_version(), 'numpy': np.__version__,
                             'pandas': pd.__version__, 'sklearn': sklearn.__version__}}
    (output / 'run_manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    plot_results(tables['metrics'], output)
    write_report(tables, manifest, output)
    print(tables['metrics'][['model', 'mae_pp']].to_string(index=False))
    print(tables['contrasts'].to_string(index=False))
    return tables, manifest


def plot_results(metrics, output):
    fig, ax = plt.subplots(figsize=(12, 6))
    table = metrics.set_index('model')
    labels = [f'{family}_{config}' for family in ['ridge', 'boosting'] for config in feature_sets()]
    x = np.arange(len(labels))
    for offset, regime in [(-.18, 'recent'), (.18, 'extended')]:
        values = [table.loc[f'{label}_{regime}', 'mae_pp'] for label in labels]
        ax.bar(x + offset, values, .36, label=regime)
    ax.set(xticks=x, xticklabels=labels, ylabel='MAE (points) · validation 2021–2022',
           title='Profondeur historique · mêmes variables et mêmes observations évaluées')
    ax.tick_params(axis='x', rotation=25)
    ax.legend()
    fig.tight_layout()
    for ext in ['png', 'svg']:
        fig.savefig(output / f'history_comparison.{ext}', dpi=180, bbox_inches='tight')
    plt.close(fig)


def write_report(tables, manifest, output):
    text = f'''# Population depuis 1981 : effet d'un entraînement plus long

Expérience rétrospective du 1er novembre 2026. Validation 2021–2022 déjà exposée,
identique pour tous les modèles ; test 2023–2025 non chargé. Paramètres fixés avant
exécution : Ridge alpha = 1, boosting aux réglages de la démonstration, sans réglage.

## Périodes réellement utilisables

{tables['partitions'].to_markdown(index=False)}

Les stocks commencent en 1981. La sélection supposée au 2 septembre Y+1 impose
un début effectif plus tardif pour les observations commune × objet disposant de
population. Les stocks invalides et correspondances non résolues sont exclus ;
les configurations sans population utilisent aussi cet échantillon, pour maintenir
la comparaison. La couverture et les exclusions sont exportées séparément.

Validation : {manifest['validation_rows']} lignes, {manifest['validation_objects']}
objets, {manifest['validation_dates']} dates. Clés identiques à la démonstration
publiée : {manifest['published_validation_keys_identical']} ; clés absentes :
{manifest['published_validation_keys_missing']}, nouvelles : {manifest['additional_validation_keys']}.

## Scores sur la même validation

Toutes les MAE sont en points de pourcentage ; plus petit est meilleur.

{tables['metrics'][['model', 'mae_pp', 'mean_object_mae_pp', 'mean_date_mae_pp']].to_markdown(index=False, floatfmt='.6f')}

## Contrastes appariés

Un gain positif signifie une baisse d'erreur. `longer_history` compare entraînement
long contre récent à variables identiques. `population_block` compare ajout des
deux variables démographiques au contexte, dans le même régime. Le gain principal
pondère chaque ligne commune × objet ; le gain moyen par date pèse chaque date
une fois. Les deltas par objet et date restent disponibles, sans intervalle de
confiance fondé sur des lignes communales supposées indépendantes.

{tables['contrasts'].to_markdown(index=False, floatfmt='.6f')}

## Sources et limites

Les stocks 1981–2009 viennent directement du bilan démographique OFS, Total et
Étranger, sexe Total ; STATPOP fournit 2010–2021. Le bilan ESPOP 2010 n'est pas
confondu avec le stock STATPOP 2010. Les CSV RTS n'entrent pas dans ce modèle.
Les sources officielles complètes sont archivées avec requêtes, dates de collecte
et empreintes. Les effectifs sont sommés avant les parts dans les fusions ; les
scissions et codes non résolus ne sont pas répartis arbitrairement. Les stocks
invalides restent des sorties annuelles explicites et ne déclenchent pas un
retour silencieux à un stock antérieur devenu caduc.

Les caractéristiques sont l'historique de vote, la population totale, la part
étrangère, la langue, l'urbanité et les quatre métadonnées d'objet. Les âges et les
parts partisanes ne sont utilisés dans aucun des deux régimes : nos données
électorales préparées ne remontent pas avant 2011. Recommandations et texte sont
également exclus. Le score du Ridge complet publié (10,697 points) portait sur
un autre ensemble de variables et ne constitue pas le contrôle isolant l'effet
historique. L'historique communal inclut les votes antérieurs à 1981 dans les deux
régimes et n'est pas recalculé en supprimant le passé du régime récent.

La règle septembre Y+1 n'est pas une preuve de publication historique. Les éditions
courantes peuvent intégrer des révisions et la géographie 2026 est rétrospective.
Les limites ESPOP et les anomalies territoriales décrites dans les audits restent
applicables. L'expérience ne rend pas les données admissibles à la V1 stricte et
ne démontre aucun effet causal ni aucune performance finale indépendante.

## Reproduction

```bash
python -m scripts.espop.population_history
python -m scripts.modeling.population_history_experiment
```

Le manifeste et toutes les sorties détaillées sont dans
`reports/generated/population_history_experiment/`. Les tables annuelles et la
table de modélisation sont distinctes, sous `data/interim/population_history/`.
Les snapshots précédents ne sont pas modifiés.
'''
    (output / 'report.md').write_text(text, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--population-dir', type=Path, default=population_source.DEFAULT_OUTPUT)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/generated/population_history_experiment')
    args = parser.parse_args()
    run(population_dir=args.population_dir, output=args.output)


if __name__ == '__main__':
    main()

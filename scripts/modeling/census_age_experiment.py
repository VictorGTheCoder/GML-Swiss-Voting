"""Add last-selectable measured ages to the population-history experiment, on paired rows."""
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
from threadpoolctl import threadpool_limits

from scripts.common.config import ROOT
from scripts.espop import census_age_history as ages
from scripts.espop import population_history as population
from scripts.integration.build_modeling_dataset import asof_join
from scripts.modeling import population_history_experiment as base
from scripts.modeling import retrospective_demo as demo

AGE_NUMERIC = ages.AGE_SHARES + ['age_measurement_age_years', 'age_missing']
AGE_CATEGORICAL = ['age_source']


def attach_ages(table, releases):
    if 'age_reference_date' in table:
        raise ValueError('Age features are already attached')
    joined = asof_join(table, releases.drop(columns='historical_availability', errors='ignore'),
                       'age_selection_from')
    selected = joined.age_selection_from.notna()
    if (selected & (joined.age_selection_from.gt(joined.feature_cutoff)
                    | joined.age_reference_date.gt(joined.feature_cutoff))).any():
        raise ValueError('A future census entered the observation')
    joined['age_measurement_age_years'] = (joined.feature_cutoff - joined.age_reference_date).dt.days / 365.25
    joined['age_missing'] = ~joined.age_valid.eq(True) | joined[ages.AGE_SHARES].isna().any(axis=1)
    joined['age_absence_reason'] = joined.age_missing_reason.fillna('no_selectable_age_release')
    joined.loc[~joined.age_missing, 'age_absence_reason'] = ''
    joined['age_reference_year'] = joined.age_reference_year.astype('Int64')
    coverage = joined.groupby(joined.vote_date.dt.year.rename('vote_year'), as_index=False).agg(
        rows=('vote_id', 'size'), objects=('vote_id', 'nunique'), missing_age_rows=('age_missing', 'sum'),
        mean_measurement_age_years=('age_measurement_age_years', 'mean'),
        max_measurement_age_years=('age_measurement_age_years', 'max'))
    if len(joined) != len(table):
        raise ValueError('Age join changed the observation population')
    return joined, coverage


def input_frame(table):
    result = base.input_frame(table)
    for c in AGE_NUMERIC:
        result[c] = table[c].astype(float)
    result['age_source'] = table.age_source.astype(object).where(table.age_source.notna(), np.nan)
    return result


def evaluate(table, output=None):
    if table.empty or not table.vote_date.between('1981-01-01', demo.VALIDATION_END).all():
        raise ValueError('Expected only observations through 2022')
    if not table.has_valid_population.all():
        raise ValueError('Expected the same population-covered rows as the base experiment')
    if table.duplicated(['municipality_id', 'vote_id']).any():
        raise ValueError('Duplicate observation keys')
    validation = table.loc[table.vote_date.gt(demo.TRAIN_END)]
    if validation.empty:
        raise ValueError('No validation observations')
    xe = input_frame(validation)
    predictions, partitions, details = [], [], []
    with threadpool_limits(limits=1):
        for regime, start in base.STARTS.items():
            train = table.loc[table.vote_date.between(start, demo.TRAIN_END)]
            if train.empty:
                raise ValueError(f'Empty training partition: {regime}')
            xt = input_frame(train)
            partitions.append({'regime': regime, 'rows': len(train), 'objects': train.vote_id.nunique(),
                               'dates': train.vote_date.nunique(), 'first_date': str(train.vote_date.min().date()),
                               'last_date': str(train.vote_date.max().date()),
                               'missing_age_rows': int(train.age_missing.sum())})
            for with_ages in [False, True]:
                numeric = base.HISTORY + base.POPULATION + (AGE_NUMERIC if with_ages else [])
                categorical = base.CATEGORICAL + (AGE_CATEGORICAL if with_ages else [])
                for family in ['ridge', 'boosting']:
                    config = 'population_age' if with_ages else 'population'
                    name = f'{family}_{config}_{regime}'
                    print(f'Fit {name}: {len(train):,} rows / {train.vote_id.nunique()} objects', flush=True)
                    model = (demo.ridge_pipeline(numeric, categorical, 1.) if family == 'ridge'
                             else base.boosting_pipeline(xt, numeric, categorical))
                    model.fit(xt, train.yes_share.astype(float))
                    raw = model.predict(xe)
                    if not np.isfinite(raw).all():
                        raise ValueError(f'Nonfinite predictions: {name}')
                    result = validation[['municipality_id', 'vote_id', 'vote_date', 'yes_share']].rename(
                        columns={'yes_share': 'target_share'}).copy()
                    result['model'], result['raw_prediction'] = name, raw
                    result['prediction'] = np.clip(raw, 0, 1)
                    result['clipped'] = raw != result.prediction
                    predictions.append(result)
                    details.append({'model': name, 'regime': regime, 'numeric': numeric, 'categorical': categorical,
                                    'missing_training_features': xt[numeric + categorical].columns[
                                        xt[numeric + categorical].isna().all()].tolist()})
                    if output is not None:
                        joblib.dump(model, Path(output) / f'{name}.joblib')
    predictions = pd.concat(predictions, ignore_index=True)
    metrics, objects, dates = demo.report_metrics(predictions)
    definitions = []
    for family in ['ridge', 'boosting']:
        for regime in base.STARTS:
            definitions.append((f'{family}_population_age_{regime}', f'{family}_population_{regime}',
                                f'age_block__{family}_{regime}'))
        for config in ['population', 'population_age']:
            definitions.append((f'{family}_{config}_extended', f'{family}_{config}_recent',
                                f'longer_history__{family}_{config}'))
    tables = {'predictions': predictions, 'metrics': metrics, 'by_object': objects, 'by_date': dates,
              'partitions': pd.DataFrame(partitions)}
    for label, source, keys, value in [('contrasts', metrics, [], 'mae_pp'),
                                       ('object_contrasts', objects, ['vote_id', 'vote_date'], 'absolute_error_pp'),
                                       ('date_contrasts', dates, ['vote_date'], 'absolute_error_pp')]:
        tables[label] = pd.concat([base.paired_contrast(source, keys, value, a, b, name)
                                   for a, b, name in definitions], ignore_index=True)
    date_summary = tables['date_contrasts'].groupby('contrast', as_index=False).agg(
        mean_date_gain_pp=('gain_pp', 'mean'), positive_dates=('gain_pp', lambda s: int(s.gt(0).sum())),
        dates=('vote_date', 'nunique'))
    object_summary = tables['object_contrasts'].groupby('contrast', as_index=False).agg(
        positive_objects=('gain_pp', lambda s: int(s.gt(0).sum())), objects=('vote_id', 'nunique'))
    tables['contrasts'] = tables['contrasts'].merge(date_summary, on='contrast', validate='one_to_one').merge(
        object_summary, on='contrast', validate='one_to_one')
    return tables, details


def run(root=ROOT, age_dir=ages.DEFAULT_OUTPUT, population_dir=population.DEFAULT_OUTPUT,
        output=ROOT / 'reports/generated/census_age_experiment'):
    root, age_dir, population_dir, output = map(Path, [root, age_dir, population_dir, output])
    previous_dir = root / 'reports/generated/population_history_experiment'
    previous_manifest = json.loads((previous_dir / 'run_manifest.json').read_text())
    age_manifest = json.loads((age_dir / 'manifest.json').read_text())
    age_path = age_dir / 'age_releases.parquet'
    if demo.sha256(age_path) != age_manifest['age_releases_sha256']:
        raise ValueError('Age preparation fingerprint mismatch')
    if age_manifest['statpop_sha256'] != previous_manifest['population_preparation']['statpop_sha256']:
        raise ValueError('Age and population experiments use different STATPOP versions')
    for source in previous_manifest['sources'].values():
        if demo.sha256(root / source['path']) != source['sha256']:
            raise ValueError(f'Changed source: {source["path"]}')
    table_path = population_dir / 'municipal_population.parquet'
    if demo.sha256(table_path) != previous_manifest['dataset_sha256']:
        raise ValueError('Population modeling table fingerprint mismatch')
    original = pd.read_parquet(table_path, filters=[('vote_date', '<=', demo.VALIDATION_END)])
    releases = pd.read_parquet(age_path)
    table, coverage = attach_ages(original, releases)
    output.mkdir(parents=True, exist_ok=True)
    table_path = age_dir / 'municipal_with_ages.parquet'
    table.to_parquet(table_path, index=False)
    tables, details = evaluate(table, output)
    previous = pd.read_csv(previous_dir / 'metrics.csv').set_index('model')
    for name in [row['model'] for row in details if '_age_' not in row['model']]:
        measured = tables['metrics'].set_index('model').loc[name, 'mae_pp']
        np.testing.assert_allclose(measured, previous.loc[name, 'mae_pp'], rtol=0, atol=1e-9)
    validation = table.loc[table.vote_date.gt(demo.TRAIN_END)]
    original_validation = original.loc[original.vote_date.gt(demo.TRAIN_END)]
    assert set(zip(validation.municipality_id, validation.vote_id)) == set(
        zip(original_validation.municipality_id, original_validation.vote_id))
    tables['age_coverage_by_vote_year'] = coverage
    tables['age_selection_counts'] = table.groupby(
        ['partition', 'age_source', 'age_reference_year', 'age_missing'], dropna=False).size().rename('rows').reset_index()
    for name, frame in tables.items():
        if name == 'predictions':
            frame.to_parquet(output / 'predictions.parquet', index=False)
        else:
            frame.to_csv(output / f'{name}.csv', index=False)
    manifest = {'mode': 'exploratory_retrospective', 'strict_forecast_ready': False,
                'validation_previously_exposed': True, 'test_evaluated': False,
                'validation_rows': len(validation), 'validation_objects': validation.vote_id.nunique(),
                'validation_dates': validation.vote_date.nunique(), 'baseline_scores_reproduced': True,
                'validation_keys_unchanged': True, 'ridge_alpha': 1., 'hyperparameter_search': False,
                'automatic_selection': False, 'age_numeric': AGE_NUMERIC, 'age_categorical': AGE_CATEGORICAL,
                'reference_year_is_metadata': True, 'age_preparation': age_manifest,
                'population_modeling_sha256': previous_manifest['dataset_sha256'],
                'sources': previous_manifest['sources'], 'preprocessing': details,
                'history_policy': previous_manifest['history_policy'],
                'dataset_sha256': demo.sha256(table_path),
                'implementation_sha256': {p.name: demo.sha256(p) for p in [Path(__file__), Path(base.__file__),
                                         Path(ages.__file__), Path(demo.__file__),
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
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), sharey=True)
    scores = metrics.set_index('model')
    x = np.arange(2)
    for family, ax in zip(['ridge', 'boosting'], axes):
        for offset, config, label in [(-.18, 'population', 'Sans âges'), (.18, 'population_age', 'Avec âges')]:
            values = [scores.loc[f'{family}_{config}_{regime}', 'mae_pp'] for regime in base.STARTS]
            ax.bar(x + offset, values, .36, label=label)
        ax.set(title=family, xticks=x, xticklabels=['Récent', 'Long'])
        ax.legend()
    axes[0].set_ylabel('MAE (points) · validation 2021–2022 déjà exposée')
    fig.suptitle('Dernière mesure d’âge sélectionnable · mêmes observations')
    fig.tight_layout()
    for ext in ['png', 'svg']:
        fig.savefig(output / f'age_comparison.{ext}', dpi=180, bbox_inches='tight')
    plt.close(fig)


def write_report(tables, manifest, output):
    report = f'''# Âges issus des recensements : intégration et comparaison

Expérience rétrospective du 1er novembre 2026. Les trois parts d'âge 0–19,
20–39 et 65+ sont calculées à partir des recensements OFS 1980/1990/2000,
puis des stocks STATPOP annuels dès 2010. Aucune interpolation entre recensements.
L'âge moyen et la part 80+ ne sont pas approximés.

## Sélection temporelle et géographie

RFP : sélection supposée au 1er janvier Y+3, soit 1983/1993/2003. Cette hypothèse
n'est pas une date de publication attestée du tableau communal. Les stocks
STATPOP sont sélectionnés à partir du 2 septembre Y+1, comme dans l'expérience
population. L'ancienne mesure reste utilisée jusqu'à la sélection d'une nouvelle.
Une nouvelle mesure exclue pour territoire ou effectifs invalides reste manquante,
sans retour silencieux à une ancienne valeur. Les âges utilisent le dénominateur
propre à leur source : population résidante RFP, permanente STATPOP. Les effectifs
des constituants prouvés d'une fusion sont sommés avant le calcul des parts ; les
scissions et allocations non prouvées sont exclues et tracées.

Le modèle reçoit trois parts, l'ancienneté de mesure en années, un indicateur
d'absence et la source. L'année et les dates exactes sont conservées en provenance.
Une part d'âge RFP de 1980 employée en 1985 reste une mesure de 1980, pas une
estimation annuelle de 1985.

## Population et résultats

Huit ajustements, mêmes paramètres que l'expérience population. Ridge alpha = 1,
boosting fixe sans early stopping ; aucun réglage ni sélection automatique.
Prétraitements ajustés sur chaque train. Les valeurs d'âge absentes ne suppriment
aucune observation ; Ridge les impute depuis le train, boosting gère les manquants.

{tables['partitions'].to_markdown(index=False)}

Validation commune : {manifest['validation_rows']} lignes, {manifest['validation_objects']}
objets et {manifest['validation_dates']} dates en 2021–2022, déjà exposée. Les quatre
scores sans âge reproduisent l'expérience précédente à moins de 1e-9 point.
Le test réservé 2023–2025 n'est pas chargé. L'historique des scrutins reste gelé
à fin 2020 dans la validation et inclut uniquement des dates strictement passées
pour chaque ligne d'entraînement.

{tables['metrics'][['model', 'mae_pp', 'mean_object_mae_pp', 'mean_date_mae_pp']].to_markdown(index=False, floatfmt='.6f')}

## Contrastes appariés

Gain positif = baisse de MAE. `age_block` isole l'ajout des âges et de leur
provenance/ancienneté dans chaque régime ; `longer_history` compare long et récent
à variables identiques. Les moyennes par date pondèrent les sept dates une fois
chacune, à distinguer de la MAE communale. Les effectifs d'objets/dates favorables
ne sont pas un test de significativité.

{tables['contrasts'].to_markdown(index=False, floatfmt='.6f')}

## Limites et reproduction

Géographie 2026 et éditions actuelles rétrospectives ; disponibilité historique
des tableaux et hypothèses de sélection non validées pour une prévision stricte.
Les observations communales sont dépendantes, la validation est réutilisée et
aucun effet causal ni résultat final indépendant n'est établi. Les mesures RFP
et STATPOP ne sont pas un même univers statistique. Le contraste concerne tout
le bloc ajouté, y compris source, absence et ancienneté, pas un effet causal des
âges pris isolément. Les âges peuvent être vieux de plus de dix ans avant le
prochain millésime sélectionnable ; la couverture et l'ancienneté sont exportées.

```bash
python -m scripts.espop.census_age_history
python -m scripts.modeling.census_age_experiment
```

Sorties : `reports/generated/census_age_experiment/` ; mesures et table enrichie :
`data/interim/census_age_history/`. Les sources et snapshots précédents restent
inchangés. Les manifestes conservent dates, paramètres, exclusions et empreintes.
'''
    (output / 'report.md').write_text(report, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--age-dir', type=Path, default=ages.DEFAULT_OUTPUT)
    parser.add_argument('--population-dir', type=Path, default=population.DEFAULT_OUTPUT)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/generated/census_age_experiment')
    args = parser.parse_args()
    run(age_dir=args.age_dir, population_dir=args.population_dir, output=args.output)


if __name__ == '__main__':
    main()

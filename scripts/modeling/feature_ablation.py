"""Cumulative fixed-Ridge feature ablation; reserved test is never evaluated.

Run from the repository root: python -m scripts.modeling.feature_ablation
"""
from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import sklearn
from threadpoolctl import threadpool_limits

from scripts.common.config import ROOT
from scripts.integration.build_modeling_dataset import DEMOGRAPHICS, OBJECT_FIELDS, PARTIES, TYPOLOGIES
from scripts.modeling.regularized_votes import _pipeline as ridge_pipeline
from scripts.modeling.retrospective_demo import (
    TRAIN_END,
    VALIDATION_END,
    load_inputs,
    sha256,
)
from scripts.modeling.vote_metrics import score_predictions

matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Cumulative groups; source definitions come from the existing table builder.
GROUPS = {
    'historique': (['history_mean_yes', 'history_n_objects', 'history_missing'], []),
    'géographie': ([], TYPOLOGIES),
    'démographie': ([f'statpop_{c}' for c in DEMOGRAPHICS] + ['statpop_missing'], []),
    'partis': ([f'party_share_{c}' for c in PARTIES.values()] + ['elections_missing'], []),
    'objets': ([], list(OBJECT_FIELDS.values())),
}


def compare(data):
    """One fit per cumulative configuration, with identical keys and fixed alpha."""
    if not data.vote_date.between('2012-01-01', VALIDATION_END).all():
        raise ValueError('Only training and validation dates are allowed')
    expected = np.where(data.vote_date.le(TRAIN_END), 'train', 'validation')
    if not np.array_equal(data.partition, expected):
        raise ValueError('Partitions must follow entire voting dates')
    if data.duplicated(['municipality_id', 'vote_id']).any():
        raise ValueError('Duplicate comparison keys')
    train = data.loc[data.partition.eq('train')]
    validation = data.loc[data.partition.eq('validation')]
    if train.empty or validation.empty:
        raise ValueError('Both periods must contain observations')
    numeric, categorical, predictions, scores, configurations = [], [], [], [], {}
    for label, (group, (num, cat)) in zip('ABCDE', GROUPS.items()):
        numeric += num
        categorical += cat
        columns = numeric + categorical
        x = data[columns].copy()
        for c in numeric:
            x[c] = x[c].astype(float)
        for c in categorical:
            x[c] = x[c].astype(object).where(x[c].notna(), np.nan)
        model = ridge_pipeline(numeric.copy(), categorical.copy(), 1.0)
        with threadpool_limits(limits=1):
            model.fit(x.loc[train.index], train.yes_share.astype(float))
            raw = model.predict(x.loc[validation.index])
        if not np.isfinite(raw).all():
            raise ValueError('Nonfinite predictions')
        frame = validation[['municipality_id', 'vote_id', 'vote_date', 'yes_share']].rename(
            columns={'yes_share': 'target_share'}).copy()
        frame['model'], frame['raw_prediction'] = label, raw
        frame['prediction'] = np.clip(raw, 0, 1)
        frame['clipped'] = raw != frame.prediction
        predictions.append(frame)
        scores.append({'configuration': label, 'ajout': group, **score_predictions(frame),
                       'raw_mae_pp': float(np.abs(raw - frame.target_share).mean() * 100)})
        configurations[label] = {'numeric': numeric.copy(), 'categorical': categorical.copy(),
            'all_missing_training': [c for c in columns if train[c].isna().all()]}
    scores = pd.DataFrame(scores)
    scores['gain_vs_A_pp'] = scores.mae_pp.iloc[0] - scores.mae_pp
    scores['gain_vs_previous_pp'] = -scores.mae_pp.diff()
    return pd.concat(predictions, ignore_index=True), scores, configurations


def run(root, output):
    output.mkdir(parents=True, exist_ok=True)
    data, source_manifest, exclusions = load_inputs(root)
    predictions, scores, configurations = compare(data)
    predictions.to_parquet(output / 'validation_predictions.parquet', index=False)
    scores.to_csv(output / 'validation_metrics.csv', index=False)
    partitions = data.groupby('partition').agg(rows=('vote_id', 'size'), objects=('vote_id', 'nunique'),
        dates=('vote_date', 'nunique'), first_date=('vote_date', 'min'), last_date=('vote_date', 'max'))
    partitions.to_csv(output / 'partitions.csv')
    manifest = {'mode': 'exploratory_retrospective', 'test_evaluated': False, 'alpha': 1.0,
        'configurations': configurations, 'groups': GROUPS, 'sources': source_manifest['sources'],
        'dataset_sha256': sha256(root / 'data/processed/modeling/municipal_structured.parquet'),
        'runner_sha256': sha256(Path(__file__)), 'source_exclusions': exclusions,
        'history_policy': 'strictly earlier dates; frozen at 2020-12-31; pre-2012 context included',
        'partition_dates': {p: sorted(g.vote_date.dt.strftime('%Y-%m-%d').unique().tolist())
                            for p, g in data.groupby('partition')},
        'versions': {'python': platform.python_version(), 'sklearn': sklearn.__version__,
                     'pandas': pd.__version__, 'numpy': np.__version__}}
    (output / 'run_manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    plt.rcParams['svg.hashsalt'] = 'feature-ablation'
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(scores.configuration, scores.mae_pp, marker='o', color='#2563a6')
    for row in scores.itertuples():
        ax.annotate(f'{row.mae_pp:.3f}', (row.configuration, row.mae_pp), xytext=(0, 10),
                    textcoords='offset points', ha='center')
    ax.set_xticks(range(5), ['A\nHistorique', 'B\n+ Géographie', 'C\n+ Démographie',
                            'D\n+ Partis', 'E\n+ Objets'])
    ax.set(ylabel='MAE (points de pourcentage) — plus bas = mieux',
           title='Ridge α = 1 · validation rétrospective 2021–2022')
    ax.margins(y=.25)
    ax.grid(axis='y', alpha=.2)
    fig.tight_layout()
    for ext in ['png', 'svg']:
        fig.savefig(output / f'ablation_mae.{ext}', dpi=180, metadata={'Date': None} if ext == 'svg' else None)
    svg = output / 'ablation_mae.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
    plt.close(fig)
    group_text = '\n'.join(f'- **{name}** : ' + ', '.join(f'`{c}`' for c in num + cat)
                           for name, (num, cat) in GROUPS.items())
    report = f'''# Première ablation des variables — Ridge

Évaluation rétrospective exploratoire, pas une prévision historique stricte.
Objectif : mesurer l'apport cumulé de cinq groupes à modèle identique.

## Données et variables

Table versionnée `data/processed/modeling/municipal_structured.parquet`, une ligne
commune × objet, cible `yes_share` (0–1), géographie rétrospective 2026.
A contient l'historique ; chaque configuration ajoute le groupe suivant :

{group_text}

A inclut aussi le nombre d'objets historiques, contrairement au Ridge historique
minimal de #70 (moyenne et indicateur seulement) : sa MAE peut donc différer.
Toutes les catégories sont disponibles. Les parts des partis restent distinctes,
les absences ne deviennent pas des zéros observés. Les colonnes entièrement vides
sur l'entraînement sont consignées dans le manifeste ; leur imputation constante
par le pipeline existant ne permet pas d'estimer leur contribution.
Les noms de colonnes, hypothèses et empreintes figurent dans `run_manifest.json`.

## Protocole

{partitions.to_markdown()}

Entraînement 2012–2020, validation 2021–2022, test 2023–2025 réservé et non évalué.
Les filtres Parquet excluent les cibles du test avant chargement. Historique recalculé
sur les résultats OFS nettoyés : dates strictement antérieures, tous les objets
du même jour exclus, contexte antérieur à 2012 inclus, validation figée fin 2020.
Aucune cible de validation n'entre dans l'historique ou l'ajustement.
Toutes les configurations conservent exactement les mêmes lignes, même avec des
valeurs manquantes. Chaque date appartient à une seule partition.

Ridge alpha=1 fixé avant exécution, référence simple déjà utilisée dans #70,
sans recherche ni choix fondé sur les scores. Réutilisation de
`regularized_votes._pipeline` : médiane puis standardisation des numériques,
modalité manquante et one-hot des catégories inconnues ignorées, indicateurs de
manque pour toutes les colonnes. Ajustement uniquement sur l'entraînement.
Prédictions bornées à [0,1], comme #70 ; MAE brute et fréquence de bornage aussi exportées.

## Résultats réels de validation

{scores[['configuration', 'ajout', 'mae_pp', 'gain_vs_A_pp', 'gain_vs_previous_pp']].to_markdown(index=False, floatfmt='.6f')}

Gain positif = baisse de MAE ; gain négatif = dégradation. Chaque ligne
commune × objet a le même poids, sans pondération par population.

![Évolution des performances](ablation_mae.png)

## Interprétation et limites

Le passage A → E change la MAE de {scores.mae_pp.iloc[0]:.6f} à
{scores.mae_pp.iloc[-1]:.6f} pp, soit un gain de {scores.gain_vs_A_pp.iloc[-1]:.6f} pp.
Les différences successives mesurent une contribution conditionnelle à l'ordre
retenu, pas une importance intrinsèque ou causale. Une amélioration de validation
ne prouve pas une meilleure généralisation.

La V1 stricte contient zéro observation admissible : les preuves de publication
historiques manquent. Les typologies 2026, les éditions actuelles STATPOP/Swissvotes,
l'harmonisation géographique rétrospective et les seuils supposés des élections
empêchent une revendication de prévision historique stricte. Les contrôles excluent
les cibles contemporaines ou futures des historiques, sans certifier les versions
historiquement publiées des autres sources. Validation limitée à 24 objets sur sept
dates ; dépendance entre communes, absence d'intervalle d'incertitude.
La validation a déjà été explorée par les travaux #70/#73.

## Existant examiné et prochaines étapes

README, contrats `modeling`/`modeling_v1`, guides V1 et évaluation municipale examinés.
#70 fournit le protocole et les contrôles de chargement/historique, réutilisés
directement depuis `retrospective_demo` ; son modèle boosting reste inchangé.
#73 (`17186d7`, `02_regularized_linear.ipynb`) explore Ridge/Lasso/Elastic Net,
plusieurs alphas, regroupements de partis et interactions. Son notebook contient
également une section test final : elle n'est ni exécutée ni utilisée ici.
Ses prétraitements et ses choix diffèrent : les scores ne sont pas directement
interchangeables avec cette expérience. Aucun résultat de test n'est exploité.

Ensuite : sélection par blocs ou Lasso dans des fenêtres chronologiques internes
à 2012–2020, avec tous les prétraitements réajustés par fenêtre ; étudier la stabilité
par date/objet et la redondance. Établir les preuves de disponibilité de la V1,
figer les choix avant toute future évaluation finale autorisée.

## Reproduction

Depuis la racine, dans l'environnement `environment.yml` :

```bash
python -m scripts.modeling.feature_ablation
```

Artefacts : ce rapport, CSV des métriques/partitions, prédictions de validation
Parquet, manifeste des variables/sources/versions et figures PNG/SVG sous
`reports/generated/feature_ablation/`. Aucun téléchargement ou changement des sources.
'''
    (output / 'report.md').write_text(report, encoding='utf-8')
    print(scores[['configuration', 'mae_pp', 'gain_vs_A_pp']].to_string(index=False))
    return predictions, scores, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/generated/feature_ablation')
    args = parser.parse_args()
    run(ROOT, args.output)


if __name__ == '__main__':
    main()

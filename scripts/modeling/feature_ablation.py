"""Cumulative, single-group and pairwise fixed-Ridge feature ablation; reserved test is never evaluated.

Run from the repository root: python -m scripts.modeling.feature_ablation
"""
from __future__ import annotations

import argparse
import json
import platform
from itertools import combinations
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


# Fixed comparisons conditional on the same four municipal groups (D).
OBJECT_VARIANTS = {
    'D': [],
    'D1': ['object_legal_form'],
    'D2': ['object_domain_1'],
    'D3': ['object_domain_1', 'object_domain_2', 'object_domain_3'],
    'E': list(OBJECT_FIELDS.values()),
}


def feature_sets():
    """Preserve A–E and add every singleton/pair, fitting duplicate sets only once."""
    names = tuple(GROUPS)
    sets = {label: names[:i] for i, label in enumerate('ABCDE', 1)}
    for size, prefix in [(1, 'S'), (2, 'P')]:
        for i, groups in enumerate(combinations(names, size), 1):
            if groups not in sets.values():
                sets[f'{prefix}{i}'] = groups
    return sets


def compare(data):
    """One fit per distinct group set, with identical keys and fixed alpha."""
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
    predictions, scores, configurations = [], [], {}
    sets = feature_sets()
    sets.update({label: sets['E'] for label in OBJECT_VARIANTS if label not in sets})
    for label, groups in sets.items():
        numeric = [c for group in groups for c in GROUPS[group][0]]
        categorical = [c for group in groups for c in GROUPS[group][1]]
        if label in OBJECT_VARIANTS:
            categorical = [c for c in categorical if c not in GROUPS['objets'][1] or c in OBJECT_VARIANTS[label]]
        description = ' + '.join(groups)
        if label in ['D1', 'D2', 'D3']:
            description = 'D + ' + ' + '.join(OBJECT_VARIANTS[label])
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
        scores.append({'configuration': label, 'ajout': groups[-1] if label in 'ABCDE' else ' + '.join(groups),
                       'groups': description, 'n_groups': len(groups), **score_predictions(frame),
                       'raw_mae_pp': float(np.abs(raw - frame.target_share).mean() * 100)})
        configurations[label] = {'groups': list(groups), 'numeric': numeric.copy(), 'categorical': categorical.copy(),
            'all_missing_training': [c for c in columns if train[c].isna().all()]}
    scores = pd.DataFrame(scores)
    scores['gain_vs_A_pp'] = scores.mae_pp.iloc[0] - scores.mae_pp
    scores['gain_vs_D_pp'] = float(scores.loc[scores.configuration.eq('D'), 'mae_pp'].iloc[0]) - scores.mae_pp
    scores['gain_vs_previous_pp'] = np.nan
    cumulative = scores.configuration.isin(list('ABCDE'))
    scores.loc[cumulative, 'gain_vs_previous_pp'] = -scores.loc[cumulative, 'mae_pp'].diff()
    return pd.concat(predictions, ignore_index=True), scores, configurations


def run(root, output):
    output.mkdir(parents=True, exist_ok=True)
    data, source_manifest, exclusions = load_inputs(root)
    predictions, scores, configurations = compare(data)
    predictions.to_parquet(output / 'validation_predictions.parquet', index=False)
    scores.to_csv(output / 'validation_metrics.csv', index=False)
    cumulative = scores.loc[scores.configuration.isin(list('ABCDE'))]
    single_pairs = scores.loc[scores.n_groups.le(2)].sort_values('n_groups', kind='stable').copy()
    single_pairs.to_csv(output / 'single_pair_metrics.csv', index=False)
    object_detail = scores.set_index('configuration').loc[list(OBJECT_VARIANTS)].reset_index()
    object_detail['object_features'] = [' + '.join(OBJECT_VARIANTS[label]) or 'aucune'
                                        for label in object_detail.configuration]
    object_detail.to_csv(output / 'object_detail_metrics.csv', index=False)
    partitions = data.groupby('partition').agg(rows=('vote_id', 'size'), objects=('vote_id', 'nunique'),
        dates=('vote_date', 'nunique'), first_date=('vote_date', 'min'), last_date=('vote_date', 'max'))
    partitions.to_csv(output / 'partitions.csv')
    manifest = {'mode': 'exploratory_retrospective', 'test_evaluated': False, 'alpha': 1.0,
        'configurations': configurations, 'groups': GROUPS, 'object_variants': OBJECT_VARIANTS,
        'sources': source_manifest['sources'],
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
    ax.plot(cumulative.configuration, cumulative.mae_pp, marker='o', color='#2563a6')
    for row in cumulative.itertuples():
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
    ranked = single_pairs.sort_values(['mae_pp', 'configuration'], kind='stable')
    fig, ax = plt.subplots(figsize=(10, 7))
    colors = ['#2563a6' if n == 1 else '#439b83' for n in ranked.n_groups]
    ax.barh(ranked.groups, ranked.mae_pp, color=colors)
    ax.invert_yaxis()
    for i, value in enumerate(ranked.mae_pp):
        ax.text(value + .07, i, f'{value:.3f}', va='center', fontsize=9)
    ax.axvline(cumulative.mae_pp.iloc[-1], linestyle='--', color='#ad4053',
               label=f"Tous les groupes (E) : {cumulative.mae_pp.iloc[-1]:.3f} pp")
    ax.set(xlim=(0, ranked.mae_pp.max() + 1.3), xlabel='MAE (points de pourcentage) — plus bas = mieux',
           title='Ridge α = 1 · validation 2021–2022\nGroupes seuls (bleu) et paires (vert)')
    ax.legend(loc='lower right')
    fig.tight_layout()
    for ext in ['png', 'svg']:
        fig.savefig(output / f'single_pair_mae.{ext}', dpi=180, metadata={'Date': None} if ext == 'svg' else None)
    svg = output / 'single_pair_mae.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(object_detail.configuration, object_detail.mae_pp, color=['#888888'] + ['#2563a6'] * 4)
    for i, row in enumerate(object_detail.itertuples()):
        ax.text(i, row.mae_pp + .1, f'{row.mae_pp:.3f}', ha='center')
    ax.set_xticks(range(5), ['D\nSans objet', 'D1\nForme juridique', 'D2\nDomaine 1',
                            'D3\nDomaines 1–3', 'E\nForme + domaines'])
    ax.set(ylim=(0, object_detail.mae_pp.max() + 1), ylabel='MAE (points de pourcentage) — plus bas = mieux',
           title='Forme juridique ou thème ?\nRidge α = 1 · validation rétrospective 2021–2022')
    fig.tight_layout()
    for ext in ['png', 'svg']:
        fig.savefig(output / f'object_detail_mae.{ext}', dpi=180, metadata={'Date': None} if ext == 'svg' else None)
    svg = output / 'object_detail_mae.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
    plt.close(fig)
    write_report(data, predictions, scores, root, output)
    print(scores[['configuration', 'groups', 'mae_pp', 'gain_vs_A_pp']].to_string(index=False))
    return predictions, scores, manifest


def verify_results(data, predictions, scores):
    """Check saved evidence before publishing a report, without fitting models."""
    keys = ['municipality_id', 'vote_id', 'vote_date']
    expected = data.loc[data.partition.eq('validation'), keys + ['yes_share']].set_index(keys).sort_index()
    models = set(feature_sets()) | set(OBJECT_VARIANTS)
    if scores.configuration.duplicated().any() or set(scores.configuration) != models or set(predictions.model) != models:
        raise ValueError('Missing or duplicate experiment configurations')
    for name, group in predictions.groupby('model'):
        actual = group.set_index(keys).sort_index()
        if actual.index.has_duplicates or not actual.index.equals(expected.index):
            raise ValueError(f'Comparison keys differ: {name}')
        np.testing.assert_allclose(actual.target_share.astype(float), expected.yes_share.astype(float), rtol=0, atol=1e-12)
        np.testing.assert_allclose(actual.prediction.astype(float), np.clip(actual.raw_prediction.astype(float), 0, 1), rtol=0, atol=1e-12)
        row = scores.loc[scores.configuration.eq(name)].iloc[0]
        measured = score_predictions(group)
        measured['raw_mae_pp'] = float((group.raw_prediction - group.target_share).abs().mean() * 100)
        for field in ['mae_pp', 'raw_mae_pp', 'rows', 'clipped_rows', 'raw_prediction_min', 'raw_prediction_max']:
            if not np.isclose(float(row[field]), float(measured[field]), rtol=0, atol=1e-9):
                raise ValueError(f'Inconsistent {field}: {name}')


def write_report(data, predictions, scores, root, output):
    """Render the existing report and evidence from verified results; no new fit."""
    verify_results(data, predictions, scores)
    results = scores.set_index('configuration')
    def count(value):
        return f'{value:,}'.replace(',', '\u202f')
    def table(labels, descriptions, reference):
        rows = results.loc[labels]
        return pd.DataFrame({
            'Configuration': labels, 'Variables': descriptions,
            'MAE (pp)': rows.mae_pp.to_numpy(),
            f'Gain vs {reference} (pp)': results.loc[reference, 'mae_pp'] - rows.mae_pp.to_numpy(),
        }).to_markdown(index=False, floatfmt='.3f')

    cumulative_table = table(list('ABCDE'), ['Historique', 'A + géographie', 'B + démographie',
        'C + partis', 'D + objets'], 'A')
    detail_table = table(list(OBJECT_VARIANTS), ['Aucune variable d’objet', 'D + forme juridique',
        'D + domaine 1', 'D + domaines 1, 2, 3', 'D + forme juridique et domaines 1, 2, 3'], 'D')
    pairs = scores.loc[scores.n_groups.le(2)].sort_values('n_groups', kind='stable')
    pairs_table = table(pairs.configuration.tolist(), pairs.groups.tolist(), 'A')

    # Read labels only; they never enter the predictive model.
    labels = pd.read_parquet(root / 'data/processed/swissvotes/swissvotes_clean.parquet',
        columns=['vote_key', 'titel_kurz_f']).rename(columns={'vote_key': 'vote_id', 'titel_kurz_f': 'Objet'})
    errors = predictions.assign(error_pp=(predictions.prediction - predictions.target_share).abs() * 100)
    by_object = errors.groupby(['vote_id', 'vote_date', 'model']).error_pp.mean().unstack('model')
    audit = by_object[['D', 'D1', 'D2', 'D3', 'E']].reset_index().merge(labels, on='vote_id', validate='one_to_one')
    audit['D3_minus_D_pp'] = audit.D3 - audit.D
    audit.to_csv(output / 'object_error_audit.csv', index=False)
    worst = audit.sort_values('D3_minus_D_pp', ascending=False).iloc[0]
    worse_count = int(audit.D3_minus_D_pp.gt(0).sum())
    worst_fraction = worst.D3_minus_D_pp / audit.D3_minus_D_pp.sum() * 100
    objects = data.drop_duplicates('vote_id')
    train_objects = objects.loc[objects.partition.eq('train')]
    validation_objects = objects.loc[objects.partition.eq('validation')]
    support = []
    for column in GROUPS['objets'][1]:
        known = train_objects[column].dropna().unique()
        support.append({'colonne': column, 'objets_train_renseignes': int(train_objects[column].notna().sum()),
            'objets_validation_renseignes': int(validation_objects[column].notna().sum()),
            'objets_validation_categorie_inconnue': int((validation_objects[column].notna() & ~validation_objects[column].isin(known)).sum())})
    support = pd.DataFrame(support)
    support.to_csv(output / 'object_category_support.csv', index=False)

    # These examples are explicitly retrospective, including the frozen training history.
    columns = ['vote_id', 'vote_date', 'municipality_id', 'statpop_year', 'statpop_pop_total',
        'language_region', 'history_mean_yes', 'object_legal_form', 'object_domain_1',
        'object_domain_2', 'object_domain_3', 'yes_share']
    examples = data.loc[data.vote_id.isin(['6550', '6410']) & data.municipality_id.isin(['0261', '5586']), columns].copy()
    if len(examples) != 4:
        raise ValueError('The four documented municipal examples are missing')
    examples.to_csv(output / 'municipal_examples.csv', index=False)
    display = pd.DataFrame({
        'Objet (date)': examples.vote_id.map({'6550': 'Cinéma (15.05.2022)', '6410': 'Eau potable (13.06.2021)'}),
        'Commune (OFS)': examples.municipality_id.map({'0261': 'Zürich (0261)', '5586': 'Lausanne (5586)'}),
        'Population (personnes)': examples.statpop_pop_total.astype(int),
        'Année STATPOP': examples.statpop_year.astype(int),
        'Historique de oui (%)': examples.history_mean_yes.astype(float) * 100,
        'Oui observés (%)': examples.yes_share.astype(float) * 100,
    }).to_markdown(index=False, floatfmt='.3f')
    train, validation = (data.loc[data.partition.eq(part)] for part in ['train', 'validation'])
    mae_D3 = float(results.loc['D3', 'mae_pp'])
    gain_all = float(results.loc['A', 'mae_pp'] - results.loc['E', 'mae_pp'])
    d3_metrics = results.loc['D3']
    feature_text = '\n'.join(f'- **{group}** : ' + ', '.join(f'`{column}`' for column in numeric + categorical)
                             for group, (numeric, categorical) in GROUPS.items())
    report = f"""# Contribution des variables à la prédiction des votations fédérales suisses

## 1. Résumé exécutif

Nous cherchons à prédire la proportion de « oui » dans chaque commune pour un objet
fédéral. Cette **étude d’ablation** compare des ensembles de variables en conservant
le même modèle Ridge et les mêmes observations de validation.

L’historique communal seul obtient **{results.loc['A', 'mae_pp']:.3f} points de pourcentage (pp)**
d’erreur moyenne absolue, contre **{results.loc['E', 'mae_pp']:.3f} pp** avec tous les groupes,
soit un gain de **{gain_all:.3f} pp**. Ajoutée au même socle communal (historique,
géographie, démographie et partis), la forme juridique améliore davantage le score
que le premier domaine politique. Les trois domaines sans
forme juridique dégradent le score : **{mae_D3:.3f} pp**. Ce résultat est confirmé,
mais sa cause reste à établir.

**Il s’agit d’une évaluation rétrospective exploratoire, pas d’une démonstration de
prévision historique ni de généralisation à de nouvelles votations.**

## 2. Contexte et question de recherche

Une **variable prédictive** (*feature*) est une information fournie au modèle pour
estimer le résultat : par exemple la population d’une commune ou le thème d’un objet.
Nous demandons : *à modèle identique, quels groupes réduisent l’erreur, et quelle
part du gain semble venir du thème politique ou de la forme juridique ?*

L’ablation consiste ici à ajouter des groupes, à les tester seuls ou par paires,
puis à décomposer les caractéristiques des objets. Elle mesure un apport
**conditionnel aux autres variables présentes**, et non une importance universelle.

## 3. Données utilisées

### Sources et unité d’observation

**Une ligne = une commune × un objet de votation.** La cible `yes_share` vaut
`oui / (oui + non)` parmi les suffrages valables ; elle est stockée entre 0 et 1.
Les abstentions ne figurent pas dans ce dénominateur.

La [table structurée versionnée](../../../data/processed/modeling/README.md) réunit :

| Groupe | Source | Ce qu’il décrit |
| --- | --- | --- |
| Historique | Résultats OFS antérieurs | Moyenne communale des « oui », nombre d’objets et absence d’historique |
| Géographie | Typologies OFS | Région linguistique et type urbain/rural, snapshot communal 2026 |
| Démographie | STATPOP | Population permanente, parts par nationalité et âge, âge moyen |
| Partis | Élections au Conseil national, OFS | Force de neuf partis à l’élection d’une année antérieure |
| Objets | Swissvotes | Forme juridique et trois champs de domaines politiques |

Les identifiants, les dates et le canton ne sont pas des prédicteurs. Il n’y a ni
texte des brochures, ni participation, ni résultat national du scrutin dans les entrées.
Les communes sont harmonisées sur la géographie 2026 : cette cohérence territoriale
est rétrospective et ne prouve pas la disponibilité historique des sources.

<details>
<summary>Liste exacte des colonnes par groupe</summary>

{feature_text}

Les indicateurs `*_missing` signalent une absence. Le pipeline ajoute aussi des
indicateurs de manque à chaque colonne sélectionnée. Les parts manquantes ne sont
pas assimilées à des forces électorales observées de zéro. `party_share_centre`
est entièrement manquante dans l’entraînement : elle ne permet pas d’estimer
l’apport de ce parti. Les classes d’âge 80+ et 65+ se recouvrent.

`object_domain_1`, `_2`, `_3` correspondent à `d1e1`, `d2e1`, `d3e1` de Swissvotes :
trois champs au **même niveau thématique large**, pas trois niveaux de précision.
« Domaine principal » désigne ici le premier champ ; ce nom ne démontre pas que son
rang soit une mesure d’importance. Les champs peuvent répéter un même domaine.

</details>

### Deux exemples réels : cinéma et eau potable

Les quatre lignes ci-dessous proviennent des entrées effectivement utilisées, avec
l’historique figé fin 2020. Les valeurs sont arrondies à trois décimales ; le
[fichier des exemples](municipal_examples.csv) conserve leur précision.

{display}

Pour la [loi sur le cinéma, 15 mai 2022](https://swissvotes.ch/vote/655.00), souvent
appelée « Lex Netflix », la clé du projet est `6550`. Les deux communes partagent
`object_legal_form=2` (référendum facultatif) et les codes de domaines `(12, 12, 4)` :
culture/religion/médias, culture/religion/médias, économie. Les deux premiers champs
répètent donc un même domaine large ; ils ne décrivent pas deux cultures distinctes.

L’[initiative pour une eau potable propre, 13 juin 2021](https://swissvotes.ch/vote/641.00)
est l’objet `6410` : forme `3` (initiative populaire), domaines `(9, 5, 5)`
(environnement/cadre de vie, agriculture, agriculture). Les intitulés et codes sont
vérifiés dans le snapshot Swissvotes ; leur sens suit le
[codebook Swissvotes, pages 4–10](https://swissvotes.ch/page/dataset/codebook-de.pdf).

Une **caractéristique d’objet** est commune à toutes ses communes ; une
**caractéristique communale** varie : Zürich est en région germanophone, Lausanne
francophone, et leurs populations et historiques diffèrent. La **cible** est le
résultat communal observé, jamais une entrée du modèle. Les populations proviennent
des années STATPOP indiquées, et ne sont pas des populations mesurées le jour du vote.
Un modèle « objets seuls » produit la même prédiction pour toutes les communes d’un
même objet : il ne peut donc pas expliquer leurs écarts internes.

## 4. Méthodologie

### Modèle et prétraitements

**Ridge** est une régression linéaire : elle combine les entrées pour estimer la
part de « oui ». Sa **régularisation** pénalise les coefficients trop grands afin
de limiter l’ajustement excessif aux données d’entraînement. Le paramètre `alpha=1`
est fixé pour toutes les configurations, comme référence de #70, sans recherche
d’hyperparamètres. Le modèle minimise une erreur quadratique pénalisée ; la MAE
sert à évaluer ses prédictions, pas à ajuster directement ses coefficients.

Une variable **catégorielle** désigne une classe sans ordre numérique pertinent,
par exemple une forme juridique. L’**encodage** la transforme en colonnes indicatrices
(*one-hot*) ; le code `3` n’est pas interprété comme supérieur au code `2`.
Les numériques manquants sont remplacés par la médiane puis standardisés
(centrés et ramenés à une échelle comparable). Les
catégories manquantes reçoivent une modalité dédiée ; une catégorie inconnue en
validation n’ajoute aucune colonne apprise. Ces traitements sont ajustés sur
l’entraînement seulement, via le [pipeline Ridge existant](../../../scripts/modeling/regularized_votes.py).

Les prédictions sont bornées à [0, 1]. Le Parquet conserve aussi les prédictions
brutes ; les CSV indiquent la MAE brute et la fréquence de bornage. Les paires concatènent les
colonnes : **aucun terme d’interaction explicite n’est ajouté**.

### Partitions et prévention des fuites

| Partition | Période prévue | Dates réellement présentes | Lignes | Objets | Dates de vote |
| --- | --- | --- | ---: | ---: | ---: |
| Entraînement | 2012–2020 | {train.vote_date.min():%d.%m.%Y}–{train.vote_date.max():%d.%m.%Y} | {count(len(train))} | {train.vote_id.nunique()} | {train.vote_date.nunique()} |
| Validation | 2021–2022 | {validation.vote_date.min():%d.%m.%Y}–{validation.vote_date.max():%d.%m.%Y} | {count(len(validation))} | {validation.vote_id.nunique()} | {validation.vote_date.nunique()} |
| Test prévu | 2023–2025 | Non chargé ni évalué par cette étude | — | — | — |

Les **21 configurations utilisent exactement les mêmes 50 520 lignes de validation**,
soit 2 105 communes pour chacun des 24 objets. Toutes les observations d’une date
restent dans la même partition. Les valeurs manquantes sont traitées sans retirer
de lignes selon la configuration.

Une **fuite de données temporelle** consiste à utiliser une information qui ne
serait connue qu’après l’instant de prévision. Les historiques sont recalculés avec
les scrutins de dates strictement antérieures : aucun autre objet du même jour.
Le contexte antérieur à 2012 est autorisé, mais ne devient pas une ligne
d’ajustement du modèle. En validation, l’historique reste figé au 31.12.2020 : les
résultats de 2021–2022 ne l’actualisent pas. Cette protection contre l’emploi des
cibles futures ne certifie pas les anciennes dates de publication des autres sources.

**État du test final.** Cette ablation ne lit ni n’évalue les cibles 2023–2025,
qui sont filtrées avant leur chargement. À l’échelle du projet, en revanche, le
[notebook de #73, commit `17186d7`](https://github.com/VictorGTheCoder/GML-Swiss-Voting/blob/17186d7827cb514fb88cd3cb5393616cc90559ec/notebooks/02_regularized_linear.ipynb)
contient une cellule de test exécutée (`execution_count=15`, sortie conservée) et
l’export `metrics_test_final.csv`. Nous n’en reprenons aucun score ici. Le test
prévu ne peut donc pas être décrit comme entièrement vierge pour l’ensemble du projet.

### Métrique et vérification

La **MAE** (*Mean Absolute Error*, erreur moyenne absolue) est la moyenne des écarts
absolus entre prédiction et observation : **MAE (pp) = (100/N) × Σ |ŷᵢ − yᵢ|**, avec
les parts entre 0 et 1. Un écart de 0,05 correspond à 5 points de pourcentage, et non
à une erreur relative de 5 %. Chaque ligne commune × objet a le même poids ; ce
n’est pas une pondération par population ou électorat.

Les 24 objets ont ici le même nombre de communes : la MAE moyenne par objet et la
MAE par ligne coïncident. Les clés, cibles et MAE ont été vérifiées à partir des
prédictions sauvegardées ; les 21 scores concordent à 10⁻⁹ pp près avec les CSV.
Les tableaux ci-dessous sont arrondis à trois décimales. Un **gain positif** indique
une réduction de MAE par rapport à la référence précisée.

## 5. Résultats

### Ajout progressif des groupes

{cumulative_table}

![MAE des configurations progressives A à E](ablation_mae.png)

*Figure 1 — Même Ridge, mêmes observations. Les intitulés A–E indiquent l’ordre
d’ajout ; une MAE plus basse est meilleure.*

A comprend la moyenne **et le nombre d’objets historiques**, ainsi que l’indicateur
de manque. Il diffère donc du Ridge historique minimal de la démonstration #70,
qui utilise uniquement moyenne et indicateur ; leurs scores ne sont pas interchangeables.

### Décomposition des variables d’objet, à socle D identique

{detail_table}

![MAE de D, D1, D2, D3 et E : forme juridique et domaines politiques](object_detail_mae.png)

*Figure 2 — Seules les variables d’objet changent. « Domaine 1 » est le premier
champ thématique ; « domaines 1–3 » utilise les trois champs au même niveau large.*

### Groupes seuls et paires

{pairs_table}

![Classement des cinq groupes seuls et des dix paires](single_pair_mae.png)

*Figure 3 — Les libellés nomment chaque ensemble, indépendamment des couleurs.
La ligne pointillée situe E, avec tous les groupes.*

Les objets seuls obtiennent **{results.loc['S5', 'mae_pp']:.3f} pp**. La meilleure paire est
historique + objets (**{results.loc['P4', 'mae_pp']:.3f} pp**), très proche de E (**{results.loc['E', 'mae_pp']:.3f} pp**).
L’écart entre ces deux dernières configurations n’est que de
**{results.loc['P4', 'mae_pp'] - results.loc['E', 'mae_pp']:.3f} pp**, sans incertitude statistique estimée.
Les configurations communes sont réutilisées : A–E, cinq groupes seuls et dix paires
représentent 18 ensembles distincts ; D1–D3 portent le total à 21.

## 6. Interprétation : constats, pistes et questions ouvertes

### Ce qui est directement mesuré

- B, C et D restent moins bons que A dans cet ordre d’ajout. C améliore légèrement B,
  mais pas assez pour dépasser A. Cela **ne signifie pas que les variables communales
  sont inutiles** : historique + objets fait mieux qu’objets seuls.
- E réduit la MAE de {gain_all:.3f} pp par rapport à A, et de
  {results.loc['D', 'mae_pp'] - results.loc['E', 'mae_pp']:.3f} pp par rapport à D.
- À socle D identique, la forme juridique seule améliore davantage le résultat que
  le premier domaine seul. Les trois domaines sans forme dégradent fortement D.
- E est le meilleur des 21 ensembles mesurés sur **cette validation**. Cela ne
  démontre ni une supériorité générale ni la cause des votes individuels.

### Le cas inhabituel de D3

La MAE de **{mae_D3:.3f} pp** est confirmée par les prédictions sauvegardées ; la liste
des entrées de D3 contient les mêmes colonnes communales que D, plus uniquement
les trois domaines. Il n’y a pas d’inversion de l’étiquette ou de la référence dans le tableau.

Le [détail par objet](object_error_audit.csv) montre que D3 est moins bon que D pour
**{worse_count} objets sur {len(audit)}**. Sur la **loi sur le CO₂ du 13.06.2021 (`6440`)**, la
MAE passe de **{worst.D:.3f} à {worst.D3:.3f} pp** (E : **{worst.E:.3f} pp**).
Cet objet est celui où la dégradation D3−D est maximale ; avec le même poids par objet,
il représente environ **{worst_fraction:.1f} % de l’écart net** de MAE entre D3 et D.
C’est un diagnostic choisi sur l’erreur, pas un exemple représentatif.

Le [comptage des catégories](object_category_support.csv), effectué sur les objets
uniques plutôt que sur leurs répétitions communales, montre que le troisième
champ est renseigné pour **12 objets d’entraînement sur 83**, contre **13 sur 24**
en validation. Trois objets de validation présentent dans ce champ un code absent
de l’entraînement. Toutefois, les trois codes de la loi sur le CO₂ sont déjà
présents dans leurs champs respectifs d’entraînement : les catégories inconnues
ne suffisent donc pas à expliquer son échec.

D3 comporte aussi **{count(int(d3_metrics.clipped_rows))} prédictions bornées** ; sa MAE brute est
**{d3_metrics.raw_mae_pp:.3f} pp**, contre {mae_D3:.3f} pp après bornage. Le bornage atténue
l’erreur ; il ne crée pas la dégradation observée.

**Interprétation plausible :** avec peu d’objets indépendants, des catégories rares,
des domaines répétés et des distributions différentes entre périodes, les effets
estimés peuvent être fragiles. Les corrélations entre forme juridique, thèmes et
autres entrées peuvent aussi modifier les coefficients lorsque des colonnes sont ajoutées.
**Non démontré :** aucune de ces pistes n’est identifiée comme la cause de D3.
Il faudrait examiner les coefficients, leur stabilité et des validations internes
par dates pour départager ces hypothèses. Le meilleur score de E n’établit pas une
interaction causale ; le Ridge utilisé reste additif dans ses colonnes encodées.

## 7. Limites et risques

- **Disponibilité historique non prouvée.** Typologies 2026, éditions actuelles des
  sources et harmonisation territoriale rétrospective. STATPOP utilise un seuil
  supposé au 2 septembre de l’année suivante, les élections une année strictement antérieure,
  sans que ces règles prouvent la publication des versions utilisées. La
  [V1 stricte](../../../docs/project/modeling_v1.md) reste à zéro observation admissible.
- **Peu de situations indépendantes.** 50 520 lignes ne représentent pas autant
  de votations : seulement 24 objets sur sept dates. Les communes d’un même objet
  partagent le contexte et les métadonnées ; elles ne sont pas indépendantes.
- **Représentativité limitée.** L’entraînement et la validation ne contiennent pas
  nécessairement les mêmes thèmes, formes ou configurations politiques. Aucun
  intervalle d’incertitude ni test de significativité n’a été produit.
- **Dépendance au modèle et à l’ordre.** Les variables peuvent être corrélées ou
  redondantes. Les effets communaux propres à chaque thème ne sont pas modélisés
  par des interactions explicites. Un résultat défavorable ici ne rend pas une
  source inutile pour un autre modèle ou un autre protocole.
- **Exploration répétée.** La validation a déjà servi à #70, #73 et aux comparaisons
  de ce rapport. Le meilleur score observé n’est pas une estimation indépendante
  après sélection ; le test prévu a par ailleurs déjà été évalué dans #73.
- **Portée agrégée.** Les résultats communaux ne permettent pas d’inférer le
  comportement individuel ni une relation causale entre variables et vote.

## 8. Prochaines étapes et reproduction

1. **Ablation inverse :** retirer successivement un groupe de E pour mesurer sa
   contribution conditionnelle aux autres, sans confondre ce test avec l’ordre A–E.
2. **Stabilité :** examiner D3 par objet, catégorie et date, puis dans des fenêtres
   chronologiques internes à 2012–2020, avec prétraitements réajustés par fenêtre.
3. **Sélection automatique limitée :** comparer une sélection par blocs ou Lasso
   dans ces fenêtres internes, puis évaluer les choix figés sans réoptimiser sur
   cette validation déjà consultée.
4. **Comparaison avec le boosting :** appliquer les mêmes ensembles et les mêmes
   lignes au modèle existant, pour tester l’effet du modèle et des interactions.
5. **Prévision stricte :** établir les preuves de publication et de géographie,
   documenter les consultations passées du test et prévoir une évaluation sur une
   période réellement non consultée avant toute conclusion confirmatoire.

Depuis la racine, dans Python 3.12 et l’environnement figé
[`requirements-demo.txt`](../../../requirements-demo.txt) :

```bash
python -m scripts.modeling.feature_ablation
```

Cette commande reproduit les modèles, les CSV, les figures et le présent rapport.
Pour vérifier les résultats sauvegardés et régénérer uniquement le rapport et ses
tables de diagnostic, **sans réentraîner** :

```bash
python -m scripts.modeling.feature_ablation --report-only
```

Le [script](../../../scripts/modeling/feature_ablation.py) réutilise le chargement et
l’historique de [#70](https://github.com/VictorGTheCoder/GML-Swiss-Voting/pull/70).
Les prétraitements et alphas de #73 diffèrent : ses scores ne sont pas des répétitions
de cette expérience et aucun résultat de son test n’est utilisé ici.

Les sorties complètes sont dans `reports/generated/feature_ablation/` :
`validation_predictions.parquet`, `validation_metrics.csv`, `single_pair_metrics.csv`,
`object_detail_metrics.csv`, `partitions.csv`, `run_manifest.json`, les trois figures
PNG/SVG et `report.md`. Le manifeste conserve empreintes des sources, configurations,
versions logicielles et dates exactes. Le contrôle éditorial ajoute
`municipal_examples.csv`, `object_error_audit.csv` et `object_category_support.csv`.
Les [CSV versionnés](validation_metrics.csv) gardent les valeurs non arrondies ; le
rapport, ses figures et les trois tables de diagnostic sont conservés dans ce même dossier
pour la lecture sur GitHub. La commande écrit dans `reports/generated/feature_ablation/` ;
la copie versionnée est à actualiser après une nouvelle exécution vérifiée.

Vérifications ciblées :

```bash
python -m pytest tests/test_feature_ablation.py tests/test_retrospective_demo.py -q
python -m ruff check scripts/modeling/feature_ablation.py tests/test_feature_ablation.py
```
"""
    (output / 'report.md').write_text(report, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/generated/feature_ablation')
    parser.add_argument('--report-only', action='store_true', help='Verify saved predictions and refresh the report without fitting')
    args = parser.parse_args()
    if args.report_only:
        data, _, _ = load_inputs(ROOT)
        predictions = pd.read_parquet(args.output / 'validation_predictions.parquet')
        scores = pd.read_csv(args.output / 'validation_metrics.csv')
        write_report(data, predictions, scores, ROOT, args.output)
    else:
        run(ROOT, args.output)


if __name__ == '__main__':
    main()

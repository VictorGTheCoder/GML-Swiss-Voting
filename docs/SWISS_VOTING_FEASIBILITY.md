# Swiss Voting ML — test de faisabilité

## Verdict

**NO-GO**. CatBoost a un gain relatif de **-2.74%** contre Ridge (-0.32 point(s) de pourcentage de MAE). L'intervalle bootstrap à 95% de la différence *MAE Ridge − MAE CatBoost*, calculé sur les votations test (unité indépendante), est [-1.82, 1.12] points. CatBoost gagne 10 votations et Ridge 12. La décision est donc fondée sur la stabilité par objet, pas sur le grand nombre de communes.

## Données utilisées

Source principale : [OFS — résultats communaux de votations fédérales](https://www.bfs.admin.ch/asset/fr/px-x-1703030000_101), cube PXWeb `px-x-1703030000_101`; démographie : [OFS STATPOP](https://www.bfs.admin.ch/asset/fr/px-x-0102010000_101), cube `px-x-0102010000_101`. Période retenue : **2011-02-13 à 2024-11-24**. Après nettoyage : **123 objets**, **2117 communes**, **260,202 lignes**.

Exclusions : l'export est d'abord limité à 212 catégories géographiques OFS non communales (Suisse/cantons/districts), puis 0 doublons commune×objet, 4371 lignes sans Oui/Non valides ou avec target hors [0,1], et 0 objets dont la couverture était inférieure à 80% de la médiane (1692 communes). Aucune commune retenue n'a moins de cinq objets (0). Les frontières communales sont celles harmonisées par l'OFS; les anciennes fusions ne sont donc pas résolues individuellement.

## Split strict par votation

| Ensemble | Période | Objets |
|---|---|---:|
| Train | 2011-02-13 — 2020-09-27 | 82 |
| Validation | 2020-11-29 — 2022-02-13 | 19 |
| Test | 2022-05-15 — 2024-11-24 | 22 |

Chaque `vote_id` est affecté une seule fois; aucun résultat communal d'une votation test ne peut apparaître à l'entraînement. Les listes exactes sont dans `data/results/split_votes.json`.

## Features et prévention des fuites

**Dataset A** : canton, région linguistique, type d'objet (règle transparente à partir du libellé officiel : initiative/référendum/loi-décret/autre), année, mois, population permanente et part étrangère STATPOP. Par prudence ex ante, c'est un unique snapshot STATPOP **2010**, antérieur à toutes les votations retenues; aucune démographie future n'est employée. Densité et âge ne sont pas inclus dans ce test rapide.

**Dataset B** (comparaison principale) ajoute, par commune, moyenne et écart-type du Oui, moyenne de participation et nombre de dates historiques. Ces agrégats sont calculés seulement sur des **dates strictement antérieures**; les autres objets du même dimanche ne sont pas utilisés. Aucun résultat national/cantonal, aucune participation de l'objet cible, aucune moyenne calculée sur les communes de la votation cible, ni texte/embedding du libellé n'entre dans le modèle. Imputation, standardisation et one-hot encoding de Ridge sont appris sur train seulement.

## Modèles

Baseline naïve : moyenne historique disponible de la commune, sinon moyenne train. Ridge : one-hot des catégorielles + variables numériques standardisées (`alpha=20`). Ridge est évalué à la fois sur Dataset A et Dataset B, ce qui isole l'apport de l'historique. CatBoost (Dataset B) utilise le meilleur de 4 réglages légers choisis uniquement sur validation : `RMSE`, profondeur 4, 71 arbres (MAE validation 12.37 pp); taux 0.05 et arrêt anticipé. Aucun test n'est utilisé pour ce choix.

## Résultats globaux sur les mêmes votations test

MAE et RMSE sont en points de pourcentage.

| model                          |   MAE_pp |   RMSE_pp |     R2 |
|:-------------------------------|---------:|----------:|-------:|
| Naive: commune historical mean |    14.44 |     17.25 | -0.043 |
| Ridge (Dataset A)              |    11.03 |     13.72 |  0.339 |
| Ridge (Dataset B)              |    11.51 |     14.36 |  0.277 |
| CatBoost (Dataset B)           |    11.82 |     14.55 |  0.257 |

## Résultats par votation et stabilité

La différence moyenne Ridge − CatBoost par objet est **-0.32 pp**, la médiane **-0.05 pp**. CatBoost gagne 10/22 objets. Meilleur objet CatBoost : *2024-11-24 Änderung des Obligationenrechts (Mietrecht: Untermiete)* (5.83 pp); pire : *2023-06-18 Bundesbeschluss über eine besondere Besteuerung grosser Unternehmensgruppen (Umsetzung des OECD/G20-Projekts zur Besteuerung grosser Unternehmensgruppen)* (21.54 pp). Le fichier `data/results/per_vote_metrics.csv` contient la distribution complète et `test_mae_by_vote.png` la visualise.

La source ne fournit pas ici de thème officiel par objet; ventilation possible par **type** (pas une preuve de généralisation thématique) :

| vote_type     |   MAE_ridge |   MAE_catboost |
|:--------------|------------:|---------------:|
| initiative    |       13.31 |          14.9  |
| law_or_decree |       10.21 |           9.33 |
| other         |       11.94 |          13.32 |

## Importance des variables CatBoost

Importance native et importance de permutation (augmentation de MAE en pp lorsque la colonne est permutée) :

| feature                 |   importance |   permutation_mae_increase |
|:------------------------|-------------:|---------------------------:|
| vote_type               |        46.6  |                      2.304 |
| historical_vote_dates   |        31.68 |                     -0.001 |
| month                   |        13.84 |                      0.281 |
| year                    |         4.76 |                      0     |
| language_region         |         2.23 |                      0.112 |
| historical_yes_mean     |         0.9  |                      0.165 |
| population              |         0    |                      0     |
| foreign_rate            |         0    |                      0     |
| historical_yes_std      |         0    |                      0     |
| historical_turnout_mean |         0    |                      0     |

## Analyse critique et recommandation GML

1. **Non-linéaire vs Ridge :** le gain est -2.74% en MAE (-0.32 pp), à interpréter avec l'IC par objet ci-dessus.
2. **Stabilité :** 10 gains contre 12 défaites; le test bootstrap évite de confondre milliers de communes et quelques dizaines de votations indépendantes.
3. **Thèmes inédits :** ce prototype n'a pas une taxonomie officielle d'objet au niveau individuel; avec seulement type + année/mois, il ne peut pas prétendre généraliser sémantiquement à un thème inédit. La ventilation par type ci-dessus est seulement descriptive.
4. **Limite structurelle :** la taille effective du problème est le nombre d'objets, non le nombre de lignes communales. Les progrès très faibles peuvent être du bruit de sélection sur peu de scrutins.
5. **Risque projet :** élevé si le gain est faible/non stable : une grande infrastructure de collecte ou de modèles complexes ne créera pas automatiquement l'information manquante sur la votation. Les historiques communaux risquent d'expliquer l'essentiel du signal spatial, tandis que les features d'objet restent pauvres.

Recommandation : si le verdict est **NO-GO**, ne pas retenir le sujet sous la forme "forecast ex ante du yes_share". Si **GO AVEC RÉSERVES**, ne le poursuivre que sous une question plus riche : construire et évaluer des descriptions *pré-vote* des objets (thème officiel, texte de brochure, positions des partis), rolling-origin multi-périodes et ablations explicites. Le score actuel seul n'est pas une justification pour 14 semaines.

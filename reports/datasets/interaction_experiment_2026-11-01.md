# Interactions et profils latents : résultats rétrospectifs internes

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

| model                             |   mean_window_mae_pp |   mean_window_gain_pp |   min_gain_pp |   max_gain_pp |   positive_windows |   windows |   mean_date_gain_pp |   positive_dates |   dates |
|:----------------------------------|---------------------:|----------------------:|--------------:|--------------:|-------------------:|----------:|--------------------:|-----------------:|--------:|
| boosting_combined                 |            13.895172 |              1.772412 |     -1.838557 |      6.247280 |                  3 |         5 |            1.523767 |               10 |      16 |
| boosting_recommendations          |            12.162698 |              3.504886 |     -0.262382 |      7.264474 |                  4 |         5 |            4.042170 |               13 |      16 |
| latent_profiles                   |            11.069353 |              4.598231 |      0.851537 |      6.526942 |                  5 |         5 |            5.117683 |               15 |      16 |
| object_mean                       |            12.574436 |              3.093148 |     -1.040452 |      6.019008 |                  4 |         5 |            3.635732 |               12 |      16 |
| ridge_combined                    |            15.667584 |              0.000000 |      0.000000 |      0.000000 |                  0 |         5 |            0.000000 |                0 |      16 |
| ridge_history                     |            15.105285 |              0.562299 |     -3.848234 |      5.356883 |                  3 |         5 |            0.868883 |               10 |      16 |
| ridge_recommendation_interactions |            18.076333 |             -2.408749 |    -10.929379 |      2.529972 |                  3 |         5 |           -2.643309 |                5 |      16 |
| ridge_recommendations             |            19.148030 |             -3.480446 |    -11.253849 |      1.701503 |                  3 |         5 |           -3.644430 |                4 |      16 |
| ridge_theme_interactions          |            15.901904 |             -0.234320 |     -0.358513 |      0.001591 |                  1 |         5 |           -0.305960 |                6 |      16 |

## Comparaisons isolant chaque ajout

Gain = MAE de référence moins MAE du candidat. Une amélioration par rapport au
Ridge combiné n'implique pas que chaque interaction ajoutée est utile : les
contrastes suivants isolent les recommandations, leurs interactions locales et
les facteurs latents.

| contrast                          | model                             | reference             |   mean_gain_pp |   min_gain_pp |   max_gain_pp |   positive_windows |   windows |
|:----------------------------------|:----------------------------------|:----------------------|---------------:|--------------:|--------------:|-------------------:|----------:|
| boosting_recommendations          | boosting_recommendations          | boosting_combined     |       1.732474 |     -4.629726 |      7.689165 |                  4 |         5 |
| boosting_vs_ridge                 | boosting_combined                 | ridge_combined        |       1.772412 |     -1.838557 |      6.247280 |                  3 |         5 |
| latent_factors                    | latent_profiles                   | object_mean           |       1.505083 |      0.507934 |      1.891990 |                  5 |         5 |
| local_recommendation_interactions | ridge_recommendation_interactions | ridge_recommendations |       1.071697 |      0.324470 |      3.033147 |                  5 |         5 |
| recommendations                   | ridge_recommendations             | ridge_combined        |      -3.480446 |    -11.253849 |      1.701503 |                  3 |         5 |
| theme_interactions                | ridge_theme_interactions          | ridge_combined        |      -0.234320 |     -0.358513 |      0.001591 |                  1 |         5 |

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

{"status": "not_evaluated", "reason": "No reviewed forecast-time corpus provided", "link_status_counts": {"UNRESOLVED": 1197}, "links_sha256": "15cf3c91bdf454125e945b6c654a5efceae185778f88712a30c9f68362a4e50e"}

Aucune brochure n'est jointe arbitrairement à un objet. Une expérience textuelle
requiert d'abord le corpus relu avec correspondances, dates et versions admissibles.

## Reproduction

```bash
python -m scripts.modeling.interaction_experiment
```

Les prédictions et scores par objet/date/fenêtre, les contrastes, la couverture,
les figures et les paramètres/empreintes sont exportés dans ce dossier. Le guide
du dépôt est `docs/project/interaction_experiment.md`.

## Empreintes de l’exécution

Environnement : python 3.12.3, numpy 2.5.4, pandas 3.1.0, sklearn 1.9.1.

Dataset SHA-256 : `c8a488826093a53f307af0b4a04627fa6d78118a8ac4b25ca8c8e097fdf8e043`.

- `interaction_experiment.py` : `a274b3318bb64b5f906bcb64e639d6f4121f255811594062af9ce3d29f56c5b3`.
- `retrospective_demo.py` : `3f201ce03bb2f6a335d2f8ed09807f0307a149dd06d06c050701e434a9ecd06e`.
- `block_selection.py` : `e57b374979b8d7a43b0b98e0d5836caf90ca3ea3182020ef58487ce481cde270`.
- `regularized_votes.py` : `80223aa7f449827413871a0d6ac4fd4f497216e730e477228c664d4602a54fc8`.

## Lecture et décision au 1er novembre 2026

Le modèle **latent_profiles** est la piste la plus prometteuse sur cette
comparaison interne : MAE moyenne annuelle 11,069 points contre 15,668 pour le
Ridge combiné, soit 4,598 points de gain. Ce gain est positif sur les cinq années
et quinze dates sur seize ; son amplitude annuelle va de 0,852 à 6,527 points.
Il ne constitue pas une estimation indépendante de performance future.

Le contraste contrôlé `latent_profiles` − `object_mean` isole l'apport des trois
axes territoriaux : ils réduisent la MAE de 1,505 point en moyenne, dans les cinq
fenêtres (gains de 0,508 à 1,892 point). Les deux modèles utilisent les mêmes
métadonnées et consignes, et apprennent leurs sorties sur les mêmes objets
uniques. Le reste du gain face au Ridge combiné ne peut donc pas être attribué
aux seuls facteurs : les consignes et la régularisation au niveau objet diffèrent
aussi. Aucune comparaison sans recommandations n'a été mesurée pour ces facteurs.

Le boosting avec recommandations atteint 12,163 points, contre 13,895 sans
recommandations. L'amélioration moyenne est de 1,732 point, positive sur quatre
années sur cinq. Le Ridge avec recommandations reste au contraire très instable
et moins bon que le combiné en moyenne. Ajouter les produits consigne × force
locale améliore ce Ridge enrichi de 1,072 point dans les cinq fenêtres, sans
suffire à dépasser le Ridge combiné en moyenne. Les croisements de thème seuls
ne sont favorables que dans une fenêtre, avec un effet moyen défavorable de
0,234 point. Ces variantes sont conservées dans le rapport, sans omission des
échecs.

Les références historique et combinée reproduisent la comparaison par blocs à
moins de 1e-10 point de MAE par fenêtre. Aucun réglage n'a été choisi à partir des
nouveaux résultats. Les paramètres et prédicteurs demeurent ceux du protocole
fixé avant exécution. Les quelques communes absentes de l'entraînement reçoivent
la moyenne d'objet prédite ; cela concerne dix lignes en 2018. Les cellules
historiques imputées au centre sont comptées dans le manifeste.

**Suite justifiée :** approfondir le modèle latent avec des ablations des
recommandations et un choix de régularisation sur des fenêtres chronologiques
internes, en conservant une évaluation finale distincte. Les fenêtres observées
ici ne deviennent pas indépendantes parce que le modèle change. La disponibilité
historique des sources reste à démontrer avant toute revendication de prévision.
L'absence de corpus textuel validé est enregistrée ; aucun résultat textuel n'est
revendiqué.

Protocole et commande : [guide](../../docs/project/interaction_experiment.md).
Sorties détaillées et graphique : `reports/generated/interaction_experiment/`.

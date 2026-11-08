# Comparaison sur la validation déjà exposée 2021–2022

Comparaison du 1er novembre 2026 demandée après les résultats internes 2016–2020.
Entraînement sur 2012–2020, évaluation sur les mêmes 50 520 observations,
24 objets et sept dates que la démonstration précédente. Les paramètres des neuf
modèles sont ceux fixés avant l'expérience interne, sans ajustement après lecture
ni nouvelle recherche d'hyperparamètres. Les données de test 2023–2025 ne sont
pas chargées. Cette validation a déjà été exposée et ne constitue donc pas une
confirmation indépendante.

## Comparaison directe

MAE en points ; mêmes clés pour tous les modèles. Le gain positif signifie une
réduction d'erreur par rapport au Ridge combiné publié. L'agrégation principale
pondère chaque ligne commune × objet de la même manière, comme la démonstration.

| model                             |    mae_pp |   mean_object_mae_pp |   mean_date_mae_pp |   gain_vs_published_ridge_pp |
|:----------------------------------|----------:|---------------------:|-------------------:|-----------------------------:|
| ridge_history                     | 13.042844 |            13.042844 |          13.274468 |                    -2.345683 |
| ridge_combined                    | 10.697160 |            10.697160 |          10.738998 |                     0.000000 |
| ridge_recommendations             | 17.176894 |            17.176894 |          16.447343 |                    -6.479733 |
| ridge_recommendation_interactions | 17.369196 |            17.369196 |          16.531586 |                    -6.672035 |
| ridge_theme_interactions          | 10.658098 |            10.658098 |          10.721300 |                     0.039063 |
| boosting_combined                 | 12.005408 |            12.005408 |          12.345127 |                    -1.308247 |
| boosting_recommendations          | 15.979873 |            15.979873 |          16.811722 |                    -5.282713 |
| object_mean                       | 11.252336 |            11.252336 |          11.291114 |                    -0.555175 |
| latent_profiles                   | 10.706700 |            10.706700 |          10.782130 |                    -0.009539 |

Les scores du Ridge combiné et du boosting de référence reproduisent les chiffres
publiés à moins de 1e-9 point. Les 11,069 points annoncés pour les profils latents
concernaient les fenêtres 2016–2020 et n'étaient pas comparables directement aux
10,697 points du Ridge sur 2021–2022.

## Reproduction et portée

Réutiliser `demo.load_inputs(ROOT)` (coupure par défaut fin 2022), joindre
uniquement les huit colonnes de recommandations autorisées avec
`experiment.attach_recommendations`, puis appeler `experiment.fit_window` sur
les partitions train et validation et `demo.report_metrics` sur ses prédictions.
Les modules sont `scripts/modeling/retrospective_demo.py` et
`scripts/modeling/interaction_experiment.py`. Les recommandations sont lues avec
filtre `vote_date <= 2022-12-31` ; le pool historique OFS reste limité à fin 2020.
Les paramètres, sources, versions et empreintes figurent dans le manifeste de
`reports/generated/interaction_validation_2021_2022/`, avec prédictions, scores
par objet/date et couverture.

Ces résultats n'autorisent pas une conclusion causale ni une revendication de
prévision stricte. Les consignes proviennent de l'édition actuelle Swissvotes et
leur disponibilité historique n'est pas prouvée. La géographie et les sources
restent rétrospectives. Aucun modèle n'est sélectionné automatiquement à partir
de cette validation déjà consultée.

## Conclusion de la comparaison

Sur la même validation 2021–2022, les profils latents atteignent 10,706700 points
contre 10,697160 pour le Ridge combiné publié : ils sont donc légèrement moins
bons de 0,009539 point. Les interactions de thème atteignent 10,658098 points,
soit un gain de seulement 0,039063 point. Aucun gain pratiquement substantiel
ni statistiquement établi n'est démontré sur cette validation réutilisée.

Le gain de 4,598 points annoncé précédemment concernait exclusivement la moyenne
annuelle des fenêtres internes 2016–2020. Il ne constitue pas une amélioration
par rapport au score publié sur 2021–2022. Les résultats internes suggèrent une
meilleure tenue du modèle latent sur plusieurs périodes anciennes ; ils ne
justifient pas de remplacer la référence publiée en affirmant qu'elle est battue.
Les modèles Ridge/boosting simplement enrichis de recommandations échouent
nettement sur cette fenêtre. Ces échecs doivent rester visibles.

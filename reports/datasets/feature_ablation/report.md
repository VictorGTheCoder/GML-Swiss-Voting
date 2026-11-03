# Première ablation des variables — Ridge

Évaluation rétrospective exploratoire, pas une prévision historique stricte.
Objectif : mesurer l'apport cumulé de cinq groupes à modèle identique, puis
comparer chaque groupe seul et les dix combinaisons de deux groupes.

## Données et variables

Table versionnée `data/processed/modeling/municipal_structured.parquet`, une ligne
commune × objet, cible `yes_share` (0–1), géographie rétrospective 2026.
A–E ajoutent successivement les groupes suivants. L'extension les teste aussi
séparément et par paires, sans interactions supplémentaires entre colonnes :

- **historique** : `history_mean_yes`, `history_n_objects`, `history_missing`
- **géographie** : `urban_rural`, `language_region`
- **démographie** : `statpop_pop_total`, `statpop_share_foreign`, `statpop_share_0_19`, `statpop_share_20_39`, `statpop_share_40_64`, `statpop_share_65_plus`, `statpop_share_80_plus`, `statpop_mean_age`, `statpop_missing`
- **partis** : `party_share_plr`, `party_share_pdc`, `party_share_ps`, `party_share_udc`, `party_share_pev`, `party_share_verts`, `party_share_pvl`, `party_share_pbd`, `party_share_centre`, `elections_missing`
- **objets** : `object_legal_form`, `object_domain_1`, `object_domain_2`, `object_domain_3`

A inclut aussi le nombre d'objets historiques, contrairement au Ridge historique
minimal de #70 (moyenne et indicateur seulement) : sa MAE peut donc différer.
Toutes les catégories sont disponibles. Les parts des partis restent distinctes,
les absences ne deviennent pas des zéros observés. Les colonnes entièrement vides
sur l'entraînement sont consignées dans le manifeste ; leur imputation constante
par le pipeline existant ne permet pas d'estimer leur contribution.
Les noms de colonnes, hypothèses et empreintes figurent dans `run_manifest.json`.

## Protocole

| partition   |   rows |   objects |   dates | first_date          | last_date           |
|:------------|-------:|----------:|--------:|:--------------------|:--------------------|
| train       | 174571 |        83 |      30 | 2012-03-11 00:00:00 | 2020-11-29 00:00:00 |
| validation  |  50520 |        24 |       7 | 2021-03-07 00:00:00 | 2022-09-25 00:00:00 |

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

| configuration   | ajout       |    mae_pp |   gain_vs_A_pp |   gain_vs_previous_pp |
|:----------------|:------------|----------:|---------------:|----------------------:|
| A               | historique  | 13.042844 |       0.000000 |            nan        |
| B               | géographie  | 13.136385 |      -0.093541 |             -0.093541 |
| C               | démographie | 13.121613 |      -0.078769 |              0.014772 |
| D               | partis      | 13.181698 |      -0.138855 |             -0.060086 |
| E               | objets      | 10.697160 |       2.345683 |              2.484538 |

Gain positif = baisse de MAE ; gain négatif = dégradation. Chaque ligne
commune × objet a le même poids, sans pondération par population.

![Évolution des performances](ablation_mae.png)

## Chaque groupe seul et toutes les paires

| configuration   | groups                   |    mae_pp |   gain_vs_A_pp |
|:----------------|:-------------------------|----------:|---------------:|
| A               | historique               | 13.042844 |       0.000000 |
| S2              | géographie               | 13.195486 |      -0.152642 |
| S3              | démographie              | 13.085905 |      -0.043062 |
| S4              | partis                   | 13.166009 |      -0.123165 |
| S5              | objets                   | 11.004411 |       2.038433 |
| B               | historique + géographie  | 13.136385 |      -0.093541 |
| P2              | historique + démographie | 13.022222 |       0.020621 |
| P3              | historique + partis      | 13.154591 |      -0.111747 |
| P4              | historique + objets      | 10.707049 |       2.335795 |
| P5              | géographie + démographie | 13.158761 |      -0.115917 |
| P6              | géographie + partis      | 13.187670 |      -0.144827 |
| P7              | géographie + objets      | 10.811237 |       2.231606 |
| P8              | démographie + partis     | 13.152882 |      -0.110038 |
| P9              | démographie + objets     | 10.882209 |       2.160635 |
| P10             | partis + objets          | 10.830453 |       2.212391 |

Cinq groupes seuls + dix paires = quinze comparaisons. A correspond déjà à
l'historique seul, B à historique + géographie : ces deux ajustements sont réutilisés,
soit dix-huit ensembles distincts au total avec A–E. Les prédictions, les colonnes
exactes et les indicateurs de valeurs manquantes sont conservés pour chaque ensemble.
Un groupe « seul » utilise seulement ses colonnes et leurs indicateurs de manque ;
aucun historique, identifiant ou date n'est ajouté implicitement.

![Groupes seuls et paires](single_pair_mae.png)

Les objets seuls donnent **11.004411 pp**. Le meilleur ensemble
parmi les groupes seuls/paires sur cette validation est **historique + objets**,
avec **10.707049 pp**, contre **10.697160 pp** pour tous les groupes.
Un modèle objets seuls produit la même prédiction pour toutes les communes d'un
objet : il ne peut pas expliquer leurs écarts internes. Le meilleur score observé
parmi ces comparaisons reste exploratoire, sans estimation indépendante après sélection.

## Interprétation et limites

Le passage A → E change la MAE de 13.042844 à
10.697160 pp, soit un gain de 2.345683 pp.
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
La validation a déjà été explorée par les travaux #70/#73. L'ajout de ces
comparaisons augmente le risque de sélectionner un résultat favorable propre à
cette période ; aucun choix automatique de variables ni d'alpha n'est effectué.

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

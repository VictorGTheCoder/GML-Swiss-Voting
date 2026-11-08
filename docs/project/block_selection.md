# Comparaison chronologique des blocs de variables

Cette expérience applique la [recherche méthodologique](../../reports/datasets/feature_selection.md)
au snapshot de la démonstration. Elle compare le Ridge historique complet, le
Ridge combiné et quatre blocs : démographie, partis, typologies et métadonnées
d'objet. Chaque bloc est ajouté à l'historique puis retiré du combiné.

## Exécution

Dans l'environnement de la [démonstration](retrospective_demo.md), depuis la racine :

```bash
python -m scripts.modeling.block_selection
```

Les sorties sont dans `reports/generated/block_selection/` : `report.md`,
`run_manifest.json`, `metrics.csv`, `by_object.csv`, `by_date.csv`,
`window_gains.csv`, `object_gains.csv`, `date_gains.csv`, `summary.csv`,
`coverage.csv`, `predictions.parquet` et le graphique `block_gains` en PNG/SVG.
Les données préparées ne sont pas modifiées. Aucun téléchargement n'est effectué.

## Protocole fixé avant exécution

- Cinq fenêtres annuelles : 2016, 2017, 2018, 2019 et 2020. Entraînement
  croissant depuis 2012 jusqu'à la dernière date de l'année précédente présente
  dans le dataset ; toutes les communes et tous les objets d'une date restent
  ensemble. Les fenêtres ultérieures peuvent apprendre des années déjà évaluées.
- Chargement du snapshot audité limité par filtre Parquet à fin 2020 ; les cibles
  de validation 2021–2022 et du test réservé ne sont pas chargées.
- Historique communal recalculé depuis la source nettoyée, incluant les scrutins
  antérieurs à 2012. Pour l'entraînement, seules les dates strictement antérieures
  à la ligne sont utilisées. Pour toute l'année évaluée, cet historique est
  gelé à la dernière date d'entraînement : aucun résultat de cette année n'entre
  dans les variables, y compris pour ses dates les plus tardives.
- Ridge alpha = 1, imputation, standardisation, indicateurs de manque et encodage
  ajustés séparément dans chaque entraînement/configuration. Aucun réglage ni
  sélection automatique. Les suppressions de blocs retirent aussi leurs
  indicateurs d'absence et leurs modalités encodées.
- Mêmes lignes évaluées pour toutes les configurations ; pas de suppression
  selon la couverture. Prédictions bornées à [0, 1], MAE en points de pourcentage.
- Gain positif = bloc utile : MAE historique moins MAE avec ajout ; MAE après
  retrait moins MAE combiné. Les deltas sont appariés par fenêtre, date et objet.
  Le résumé distingue moyenne à poids égal par année et moyenne à poids égal
  par date. Minima/maxima ne sont pas des intervalles de confiance.

## Interprétation

Les résultats concernent ce Ridge et ses paramètres. Un bloc peut apporter de
l'information seul tout en étant redondant dans le combiné ; son utilité peut
varier selon l'année ou l'objet. Les sorties de couverture comptent séparément
les valeurs observées et signalent les colonnes entièrement manquantes avant
imputation. Elles ne prouvent pas la disponibilité historique des sources.

La géographie fixe 2026 et les versions historiques non démontrées maintiennent
l'analyse dans le régime rétrospectif. La V1 stricte reste inchangée. Les nombreuses
lignes communales ne sont pas des objets indépendants ; les fenêtres partagent
leurs entraînements. Aucun score final indépendant ni effet causal n'est établi.
Cette expérience n'exécute pas encore de permutation : son schéma d'échange et
ses contraintes de disponibilité doivent être définis séparément.

Les [résultats mesurés](../../reports/datasets/block_selection_2026-11-01.md)
consignent la comparaison ; les sorties détaillées restent régénérables.

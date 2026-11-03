# Première ablation des variables

Étude rétrospective exploratoire à Ridge identique (alpha=1), sans sélection
sur le test réservé. Le [rapport exécuté](../../reports/datasets/feature_ablation/report.md)
contient les tableaux A–E, les cinq groupes seuls et les dix paires, les figures,
les colonnes exactes et les limites. Les deux configurations communes avec A–E
sont réutilisées : dix-huit ensembles distincts de groupes complets sont ajustés.
Trois variantes supplémentaires D1–D3 distinguent forme juridique, domaine principal
et trois domaines, chacun ajouté au même socle D ; D et E sont réutilisés
(vingt et un modèles distincts au total).

Depuis la racine, dans l'environnement du projet (`environment.yml`), ou dans
l'environnement figé Python 3.12 / `requirements-demo.txt` décrit dans le
[guide de démonstration](retrospective_demo.md#install-and-run) :

```bash
python -m scripts.modeling.feature_ablation
python -m pytest tests/test_feature_ablation.py -q
```

Les sorties complètes sont dans `reports/generated/feature_ablation/` : rapport,
figures PNG/SVG, métriques CSV, partitions CSV, manifeste avec empreintes et versions,
prédictions Parquet. `single_pair_metrics.csv` et `single_pair_mae.png`/`.svg`
isolent les quinze comparaisons de groupes seuls/paires.
`object_detail_metrics.csv` et `object_detail_mae.png`/`.svg` comparent D, D1, D2,
D3 et E, avec le gain de MAE par rapport à D. Les fichiers sous `reports/datasets/feature_ablation/` sont
une copie de présentation versionnée du rapport, des métriques et des figures.
Après réexécution, les mettre à jour depuis le dossier généré si nécessaire.

Entraînement 2012–2020 ; validation 2021–2022 sur les mêmes 50 520 observations
pour chaque ensemble ; aucune évaluation 2023–2025. Les paires concatènent les
colonnes des deux groupes, sans ajouter de termes d’interaction. Le chargement et le recalcul de l'historique
réutilisent directement les contrôles bornés de `retrospective_demo` dans #70 ;
le pipeline Ridge est réutilisé directement depuis `regularized_votes`.
Cette extension complète #70 sans collecte ni reconstruction de dataset. #73 reste inchangée.
La V1 stricte reste inadmissible ; ces résultats ne démontrent pas la prévision
historique ni la généralisation.

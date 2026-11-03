# Première ablation des variables

Étude rétrospective exploratoire à Ridge identique (alpha=1), sans sélection
sur le test réservé. Le [rapport exécuté](../../reports/datasets/feature_ablation/report.md)
contient le tableau, la figure, les colonnes exactes et les limites.

Depuis la racine, dans l'environnement du projet (`environment.yml`) :

```bash
python -m scripts.modeling.feature_ablation
python -m pytest tests/test_feature_ablation.py -q
```

Les sorties complètes sont dans `reports/generated/feature_ablation/` : rapport,
figures PNG/SVG, métriques CSV, partitions CSV, manifeste avec empreintes et versions,
prédictions Parquet. Les fichiers sous `reports/datasets/feature_ablation/` sont
une copie de présentation versionnée du rapport, des métriques et des figures.
Après réexécution, les mettre à jour depuis le dossier généré si nécessaire.

Entraînement 2012–2020 ; validation 2021–2022 sur les mêmes 50 520 observations
pour A–E ; aucune évaluation 2023–2025. Le chargement et le recalcul de l'historique
reprennent les contrôles bornés de la PR #70 (`462885c`), absents de main au départ ;
le pipeline Ridge est réutilisé directement depuis `regularized_votes`.
Aucune collecte, reconstruction de dataset ou modification des PR #70/#73.
La V1 stricte reste inadmissible ; ces résultats ne démontrent pas la prévision
historique ni la généralisation.

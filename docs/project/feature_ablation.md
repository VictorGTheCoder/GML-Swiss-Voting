# Première ablation des variables

Étude rétrospective exploratoire à Ridge identique (alpha=1), sans sélection
sur le test réservé. Le [rapport exécuté](../../reports/datasets/feature_ablation/report.md)
contient le tableau, la figure, les colonnes exactes et les limites.

Depuis la racine, dans l'environnement du projet (`environment.yml`), ou dans
l'environnement figé Python 3.12 / `requirements-demo.txt` décrit dans le
[guide de démonstration](retrospective_demo.md#install-and-run) :

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
réutilisent directement les contrôles bornés de `retrospective_demo` dans #70 ;
le pipeline Ridge est réutilisé directement depuis `regularized_votes`.
Cette extension complète #70 sans collecte ni reconstruction de dataset. #73 reste inchangée.
La V1 stricte reste inadmissible ; ces résultats ne démontrent pas la prévision
historique ni la généralisation.

# Notebooks d'exploration

Ouvrir les notebooks avec l'environnement `swiss-votes-ml`. Ils retrouvent la racine
via `environment.yml` et lisent les fichiers déjà préparés : aucun téléchargement
n'est effectué dans les cellules. Les analyses OFS et électorales nécessitent les
tables `interim/`, reconstruites par le pipeline.

- [Votations OFS](datasets/ofs_votes/eda.ipynb) : couverture, valeurs manquantes et contrôles qualité.
- [Élections](datasets/elections/eda.ipynb) : présence des partis, données manquantes et pourcentages.
- [Brochures](datasets/federal_explanations/eda.ipynb) : couverture et qualité d'extraction.
- [Première expérience HistGradientBoostingRegressor](modeling/01_hist_gradient_boosting.ipynb) : contrôles, partitions chronologiques, historique figé, entraînement et comparaison aux baselines sur la validation rétrospective ; test réservé.

Préparation depuis la racine : `python -m scripts.run_pipeline --all`.
Les graphiques exportés vont dans `reports/generated/`, ignoré par Git.
Les notebooks OFS historiques dépendant du CSV API ont été remplacés par l'analyse
du pipeline PX ; il n'existe plus de collecte concurrente dans les notebooks.

# Résultats OFS des votations fédérales

`votes_communes.parquet` contient les résultats communaux nettoyés et validés du cube PX de l'OFS.

- **Une ligne** : une commune (ou unité spéciale) pour un objet de votation.
- **Identifiants** : `municipality_id`, `vote_id` et `vote_key`, avec la date, les titres et le canton.
- **Mesures** : électeurs inscrits, bulletins rentrés et valables, nombres de oui et de non, participation et pourcentages OFS.
- **Cible** : `yes_share = votes_yes / (votes_yes + votes_no)`, exprimée entre 0 et 1. `turnout` est également une proportion.
- **Indicateurs** : résultats provisoires, unités spéciales, questions subsidiaires et incohérences conservées avec un signalement.

Pour une question subsidiaire, `yes_share` représente la préférence pour l'initiative face au contre-projet, et non un taux d'approbation ordinaire.

Les données restent séparées des autres sources. La préparation des correspondances est stockée dans `data/interim/integration/`.

Reconstruction depuis la racine du dépôt : `python -m scripts.run_pipeline`.

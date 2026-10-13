# Métadonnées Swissvotes

`swissvotes_clean.parquet` contient une ligne par objet de votation, avec les colonnes retenues pour le projet après nettoyage.

- **Identifiants** : `swissvotes_id`, `vote_key` et `vote_date`. La clé commune correspond exactement au numéro Swissvotes multiplié par 10.
- **Description** : titres, mots-clés, forme juridique et codes des domaines politiques.
- **Contexte** : positions politiques, recommandations, procédure, campagne, médias et financement lorsque disponibles.
- **Indicateurs** : question subsidiaire et votation future ; le lien `swissvoteslink` permet de retrouver la fiche source.

Les colonnes entièrement vides, résultats nationaux/cantonaux, indicateurs de qualité de ces résultats, date d'entrée en vigueur, liens secondaires et doublons d'identifiant/date sont exclus. Les colonnes seulement peu renseignées sont conservées.

La table nettoyée complète reste dans `data/interim/swissvotes/swissvotes_clean.parquet`. Le détail de la sélection est généré dans `reports/swissvotes_column_selection.csv`.

Ce fichier n'est pas encore une matrice de prédicteurs : les catégories doivent être encodées et la disponibilité des variables avant la date de prédiction vérifiée. Aucune fusion avec les autres datasets n'est effectuée.

Reconstruction depuis la racine du dépôt : `python -m scripts.swissvotes.clean_swissvotes` (CSV brut requis).

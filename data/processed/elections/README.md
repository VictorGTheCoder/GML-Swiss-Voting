# Force des partis au Conseil national

`elections_communes.parquet` contient une ligne par commune (ou unité spéciale),
année d'élection et parti, pour 2011, 2015, 2019 et 2023.

- `municipality_id` : code OFS officiel, chaîne sur quatre caractères, comme dans les votations.
- `election_year`, `party_code`, `party_name` : année et identification du parti.
- `party_votes`, `party_strength_pct`, `party_share` : suffrages, pourcentage et proportion.
- `is_special_unit` : code OFS supérieur ou égal à 9000.
- `available_from` reste manquant et `availability_status` vaut `UNVERIFIED` :
  les dates historiques de publication ne sont pas prouvées par la collecte actuelle.

Le cube source utilise les communes au **01.07.2023** (note officielle du PX).
Les codes sont convertis vers le **01.01.2026** avec le répertoire des mutations.
Les suffrages sont additionnés puis les pourcentages recalculés sur le total des
suffrages de la commune regroupée ; les pourcentages ne sont jamais additionnés.
Les données absentes ne sont pas remplacées par zéro : si une composante manque
dans une fusion, le résultat de ce parti reste manquant (`source_values_missing`).
La table dans la géographie source est conservée dans
`interim/elections/elections_communes_2023_geography.parquet` et la correspondance
dans `interim/elections/commune_crosswalk.parquet`.

Cette géographie harmonisée est rétrospective ; elle ne prouve pas la disponibilité
historique des territoires ni des résultats avant chaque scrutin.

Le CSV brut et ses métadonnées restent dans `data/raw/`. La version Parquet complète,
districts inclus, se trouve dans `data/interim/elections/elections_all_levels.parquet`.

Reconstruction depuis la racine du dépôt :

```bash
python -m scripts.elections.collect_elections_conseil_national
python -m scripts.elections.build_election_features
```

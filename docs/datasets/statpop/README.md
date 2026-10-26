# OFS — STATPOP

Population résidante permanente par commune, nationalité et âge. Le dataset reste séparé des résultats de votations ; la jointure se fait ensuite par code commune.

## Source

Cube PXWeb `px-x-0102010000_101` de l'OFS, millésime du 20.08.2026 (années 2010 à 2025). Le téléchargement utilise désormais **l'export PX complet** (environ 153 Mo), conservé intact dans `data/raw/statpop/`. Il est lu progressivement pour extraire les CSV annuels sans charger tout le cube en mémoire. Les neuf années 2010–2018 déjà obtenues par l'API ont été comparées cellule par cellule : elles sont identiques.

Le mode `--method api` conserve la collecte par lots de 100 communes comme solution de repli, mais peut prendre plus d'une heure à cause des réponses 429 et des délais du serveur. Le PX et les CSV existants sont réutilisés sans `--force` ; leur cohérence est vérifiée avant réutilisation.

## Scripts

Tous les modules sont dans `scripts/statpop/` :

- `download_statpop.py` : un CSV par année dans `data/raw/statpop/` (communes seulement, population permanente, sexes confondus, nationalité totale/Suisse/étranger, âge à l'année), avec `provenance.json`.
- `parse_statpop_px.py` : extraction progressive du PX et comparaison exacte des CSV déjà présents.
- `convert_statpop_to_parquet.py` : `data/interim/statpop/statpop.parquet`, une ligne par année × commune × nationalité, colonnes `age_0` à `age_100` (la dernière est « 100 ans ou plus ») et `total`.
- `build_statpop_features.py` : `data/processed/statpop/statpop_features.parquet`.

## Géographie

Les 16 fichiers sont exprimés sur les **frontières de 2025** (mêmes 2115 codes chaque année). Les codes sont convertis vers la géographie du 01.01.2026 (celle du cube des votations) avec la correspondance de `scripts/repertoire_communes/`, et les effectifs sont sommés avant le calcul des parts. Sept codes changent : 700 → 6831 (Moutier), 2016 et 2027 → 2056, 2278 → 2262, 4122 → 4095, 2520 et 2529 → 2525. Résultat : 2110 communes × 16 années, sans valeur manquante, âges sommant au total.

## Variables produites

`pop_total`, `pop_foreign`, `share_foreign`, `pop_0_19`, `pop_20_39`, `pop_40_64`, `pop_65_plus`, `pop_80_plus`, les parts correspondantes (`share_*`) et `mean_age`, avec la colonne `available_from`.

## Disponibilité avant scrutin

L'OFS publie les résultats définitifs par commune de l'année Y fin août de l'année Y+1 (catalogue OFS : 2019 le 27.08.2020, 2020 le 01.09.2021, 2021 le 25.08.2022, 2022 le 24.08.2023, 2023 le 22.08.2024, 2024 le 27.08.2025, 2025 le 20.08.2026). Seuls des résultats provisoires **par canton** sortent en avril.

`available_from` vaut donc le **2 septembre de l'année Y+1** (lendemain de la publication la plus tardive observée). Les années 2010 à 2018 sont supposées suivre le même calendrier : leurs dates ne figurent plus dans le catalogue.

Conséquences, mesurées sur le cube des votations du 21.08.2026 :

- 47 dates de votation sur 191 (27,8 % des lignes commune × scrutin) ont une année STATPOP utilisable, à partir du 11.03.2012 ; avant, aucune feature démographique n'est admissible.
- L'année 2025 n'est utilisable pour aucune votation du cube.
- Les fichiers contiennent le millésime de 2026 : les années 2010 à 2024 ont pu être révisées depuis leur première publication, ce qui laisse un risque faible de fuite temporelle (les anciennes éditions ne sont plus disponibles pour le mesurer).

## Reproduction

```bash
python -m scripts.statpop.download_statpop
python -m scripts.statpop.convert_statpop_to_parquet
python -m scripts.statpop.build_statpop_features
```

Dépend de `scripts/repertoire_communes/` (snapshot 2026 et mutations) : exécuter d'abord `python -m scripts.repertoire_communes.download_repertoire`.

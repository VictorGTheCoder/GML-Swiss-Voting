# Démographie communale STATPOP

`statpop_features.parquet` : une ligne par commune et année, avec les effectifs,
parts par âge et nationalité, âge moyen et date conservatrice `available_from`.
`municipality_id` est une chaîne OFS sur quatre caractères compatible avec les
votations ; `commune_code` conserve le code utilisé par le pipeline communal.

La géographie est harmonisée au 01.01.2026. Le millésime téléchargé est rétrospectif :
une jointure technique réussie ne démontre pas la disponibilité historique exacte.

Voir [la documentation STATPOP](../../../docs/datasets/statpop/README.md).

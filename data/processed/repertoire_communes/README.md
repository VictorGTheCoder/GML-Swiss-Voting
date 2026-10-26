# Correspondance des communes

`crosswalk_2010-01-01_to_2026-01-01.parquet` relie les communes de 2010 à celles de
2026 à partir des mutations officielles. Les colonnes `source_code` et `target_code`
sont des chaînes OFS sur quatre caractères ; les dates sont typées. Le CSV original
est également conservé. Les snapshots et mutations complets sont dans `interim/`.

Ce fichier est une correspondance technique, pas une feature. Il ne permet pas
d'additionner directement des pourcentages ou de pondérer des scissions.

Reconstruction : `python -m scripts.repertoire_communes.commune_crosswalk`.
Voir [la documentation du répertoire](../../../docs/datasets/repertoire_communes/README.md).

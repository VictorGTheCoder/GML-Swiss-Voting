# Explications du Conseil fédéral

Snapshot des brochures officielles de la Chancellerie fédérale pour la période 2011–2026. Les textes et leur provenance sont conservés dans cinq tables séparées.

- `objects.parquet` : une ligne par objet OFS, avec sa date, la couverture par les brochures et les statuts de validation.
- `sections.parquet` : une ligne par section extraite, avec titre, texte, résumé, recommandations et références aux pages sources.
- `pages.parquet` : une ligne par page, avec texte extrait, méthode d'extraction et éventuelles erreurs.
- `sources.parquet` : une ligne par document source, avec URL, date de collecte, empreinte SHA-256 et statuts d'extraction et de disponibilité.
- `section_links.parquet` : liens candidats entre `object_id` (section) et `vote_id` (objet OFS), avec justification et statut. Plusieurs sections peuvent correspondre à un objet, et inversement.

Aucune variable Swissvotes ni résultat communal OFS n'est exporté ici. Un lien candidat ou une extraction réussie ne constitue pas une validation de la correspondance ou de la disponibilité avant le vote.

Les audits techniques restent dans `interim/`. Ce snapshot versionné n'est pas reconstruit par la pipeline OFS/Swissvotes ; la procédure dédiée est décrite dans la [documentation du dataset](../../../docs/datasets/federal_explanations/README.md).

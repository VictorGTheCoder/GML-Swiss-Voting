# Documentation

Six sources de données et le répertoire technique des communes alimentent le projet.
La table exploratoire dérivée reste distincte des sources et du protocole de prévision stricte.

## Projet

- [Datasets retenus](project/datasets.md) — rôle, granularité et règles temporelles des sources Must.
- [Audit des features communales](project/communal_features_audit.md) — inventaire et faisabilité des variables communales.
- [Table exploratoire structurée](../data/processed/modeling/README.md) — jointures, hypothèses et reconstruction.
- [Préparation V1](project/modeling_v1.md) — 30 candidates, provenance et population stricte séparée.
- [Audit V1](project/modeling_v1_audit.md) — état historique et intégration sur les sources actuelles.
- [Évaluation municipale](project/municipal_evaluation.md) — contrat strict et séparation temporelle.
- [Blocs de variables](project/municipal_features.md) — comparaison indépendante des sources.
- [Évaluation finale](project/final_evaluation.md) — gel de l'expérience et test réservé.
- [Export textuel](project/forecast_text_export.md) — admissibilité des brochures.
- [Expériences V2](project/municipal_v2.md) — modèles, sondages, commandes et prévision future.
- [Méthodologie V2](project/municipal_v2_methodology.md) — validation, sélection et limites.
- [Audit des données V2](project/municipal_v2_data_audit.md) — couverture et disponibilité.
- [Résultats V2 du 23 novembre 2026](../reports/datasets/municipal_v2_20261123/report.md) — décisions et registre des essais.
- [Investigation V3](project/municipal_v3.md) — données supplémentaires, redondances, prototypes et reproduction.
- [Résultats V3 du 23 novembre 2026](../reports/datasets/municipal_v3_20261123/report.md) — comparaisons contrôlées, incertitudes et prochaines acquisitions.

## Datasets

Les READMEs des tables versionnées décrivent leur format ; les guides détaillés
expliquent les sources, la reconstruction et les limites.

- [Explications du Conseil fédéral](datasets/federal_explanations/README.md)
- [ESPOP — sources et reproduction de l'audit historique](datasets/espop/README.md)
- [Répertoire historique des communes](datasets/repertoire_communes/README.md)
- [STATPOP](datasets/statpop/README.md)
- [Typologies territoriales et régions linguistiques](datasets/typologies/README.md)
- [Résultats OFS](../data/processed/ofs-votes/README.md)
- [Swissvotes](../data/processed/swissvotes/README.md)
- [Sondages historiques V3](../data/external/polls_historical_v3/README.md)
- [Enrichissement des objets V3](../data/processed/municipal_v3/README.md)
- [Élections au Conseil national](../data/processed/elections/README.md)

Voir aussi [l'index des notebooks](../notebooks/README.md).

Les rapports de résultats et audits datés ne sont pas stockés ici : voir `reports/datasets/`.

# Documentation

Six sources de données et le répertoire technique des communes alimentent le projet.
La table exploratoire dérivée reste distincte des sources et du protocole de prévision stricte.

## Projet

- [Datasets retenus](project/datasets.md) — rôle, granularité et règles temporelles des sources Must.
- [Audit des features communales](project/communal_features_audit.md) — inventaire et faisabilité des variables communales.
- [Table exploratoire structurée](../data/processed/modeling/README.md) — jointures, hypothèses et reconstruction.
- [Évaluation municipale](project/municipal_evaluation.md) — contrat strict et séparation temporelle.
- [Blocs de variables](project/municipal_features.md) — comparaison indépendante des sources.
- [Évaluation finale](project/final_evaluation.md) — gel de l'expérience et test réservé.
- [Export textuel](project/forecast_text_export.md) — admissibilité des brochures.

## Datasets

Les READMEs des tables versionnées décrivent leur format ; les guides détaillés
expliquent les sources, la reconstruction et les limites.

- [Explications du Conseil fédéral](datasets/federal_explanations/README.md)
- [Répertoire historique des communes](datasets/repertoire_communes/README.md)
- [STATPOP](datasets/statpop/README.md)
- [Typologies territoriales et régions linguistiques](datasets/typologies/README.md)
- [Résultats OFS](../data/processed/ofs-votes/README.md)
- [Swissvotes](../data/processed/swissvotes/README.md)
- [Élections au Conseil national](../data/processed/elections/README.md)

Voir aussi [l'index des notebooks](../notebooks/README.md).

Les rapports de résultats et audits datés ne sont pas stockés ici : voir `reports/datasets/`.

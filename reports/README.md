# Reports

Ce dossier contient des **rapports humains versionnés** : audits datés, synthèses de résultats et, plus tard, éléments destinés au rapport final.

## Organisation

```text
reports/
├── presentation/   # figures PNG de la présentation (scripts.integration.presentation_figures)
├── datasets/
│   └── <dataset>/
│       └── audit_YYYY_YYYY.md
└── generated/
    └── ...  # figures et sorties régénérables, non versionnées
```

Les tables sources Parquet, caches et données intermédiaires appartiennent à
`data/`. Les preuves finales d'une expérience (métriques, configurations,
signatures et registre des essais) peuvent accompagner son rapport pour rendre
ses chiffres vérifiables. Les grandes sorties de calcul restent sous `generated/`.

### Datasets disponibles

- [Enrichissement V3 — campagne du 23 novembre 2026](datasets/municipal_v3_20261123/report.md).
- [Modèles V2 — campagne du 23 novembre 2026](datasets/municipal_v2_20261123/report.md).
- [Bilan du pipeline au 26 octobre 2026](datasets/pipeline_validation_2026-10-26.md).
- [ESPOP — prototype de réutilisation indépendant](datasets/espop/reuse_2026-10-27.md).
- [V1 — audit de préparation et intégration](../docs/project/modeling_v1_audit.md).
- [ESPOP — faisabilité d'une extension 1981–2010](datasets/espop/audit_1981_2010.md).
- [Archive — brochures, audit du 6 octobre 2026](datasets/federal_explanations/audit_2011_2026.md).

Rapports régénérables : `generated/dataset_compatibility/audit.md` pour les sources,
`generated/modeling_dataset/report.md` pour la table exploratoire. Les manifestes
et dictionnaires nécessaires à cette dernière restent versionnés avec son Parquet.

Les rapports OFS et Swissvotes produits par `scripts/run_pipeline.py` sont générés à la racine de ce dossier et ignorés par Git. Ils sont recréés à chaque exécution.

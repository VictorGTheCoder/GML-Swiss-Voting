# Explications du Conseil fédéral

Ce dataset contient uniquement les données issues des brochures officielles de la Chancellerie fédérale nécessaires au projet.

Swissvotes est utilisé dans le pipeline comme outil auxiliaire de contrôle d'identifiants. Ses thèmes, types juridiques et positions politiques ne sont pas exportés ici : ils appartiendront au dataset Swissvotes séparé.

## Snapshot versionné

Le dossier data/processed/federal_explanations contient cinq tables :

- objects.parquet : raccordement minimal aux vote_id OFS et statuts de validation
- sections.parquet : texte, résumés et recommandations extraits
- pages.parquet : texte page par page et méthode native/OCR
- sources.parquet : provenance des brochures
- section_links.parquet : liens candidats entre sections et vote_id

## Reproduction

Le pipeline complet écrit d'abord ses artefacts techniques dans data/interim/federal_explanations_audit :

    python scripts/audit_federal_explanations_period.py --ofs data/processed/votes_communes.parquet --swissvotes data/raw/swissvotes.csv --sources data/raw/federal_explanations_sources.json --source-version 'DATASET CSV YYYY-MM-DD' --output data/interim/federal_explanations_audit

Puis le snapshot propre est construit avec :

    python scripts/build_federal_explanations_snapshot.py --input data/interim/federal_explanations_audit --output data/processed/federal_explanations

L'EDA se trouve dans notebooks/datasets/federal_explanations/eda.ipynb.

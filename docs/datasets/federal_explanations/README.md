# Explications du Conseil fédéral

Ce dataset contient uniquement les données issues des **brochures officielles de la Chancellerie fédérale** nécessaires au projet.

Swissvotes est utilisé dans le pipeline comme **outil auxiliaire de contrôle des identifiants**, mais ses thèmes, types juridiques et positions politiques ne sont pas exportés dans ce snapshot. Ils appartiendront au dataset Swissvotes séparé.

## Snapshot versionné

Le dossier \`data/processed/federal_explanations/\` contient uniquement cinq tables :

- \`objects.parquet\` — raccordement minimal entre les objets OFS et les brochures/sections ;
- \`sections.parquet\` — texte des sections extraites, résumés et recommandations ;
- \`pages.parquet\` — texte extrait page par page et méthode native/OCR ;
- \`sources.parquet\` — provenance des brochures ;
- \`section_links.parquet\` — liens candidats entre sections et \`vote_id\` OFS.

Il ne contient **ni résultats communaux OFS, ni features Swissvotes, ni rapports, ni JSON d'audit, ni tables de debug**.

## Reproduction

Le pipeline complet produit d'abord ses artefacts techniques dans \`data/interim/federal_explanations_audit/\` :

\`\`\`bash
python scripts/audit_federal_explanations_period.py \
  --ofs data/processed/votes_communes.parquet \
  --swissvotes data/raw/swissvotes.csv \
  --sources data/raw/federal_explanations_sources.json \
  --source-version 'DATASET CSV YYYY-MM-DD' \
  --output data/interim/federal_explanations_audit
\`\`\`

On construit ensuite le snapshot propre et partagé :

\`\`\`bash
python scripts/build_federal_explanations_snapshot.py \
  --input data/interim/federal_explanations_audit \
  --output data/processed/federal_explanations
\`\`\`

## EDA

Le notebook \`notebooks/datasets/federal_explanations/eda.ipynb\` lit directement ces cinq tables. Les figures générées restent dans \`reports/generated/\` et ne sont pas versionnées.

## Audit

Le résumé humain de l'audit 2011–2026 reste dans :

\`reports/datasets/federal_explanations/audit_2011_2026.md\`

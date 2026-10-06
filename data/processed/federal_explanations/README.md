# Federal explanations processed snapshot

Snapshot du pipeline **Explications du Conseil fédéral**, généré lors de l'audit du **6 octobre 2026** pour la période **2011–2026**.

Ce dossier est volontairement versionné afin que les membres de l'équipe puissent utiliser le dataset et exécuter l'EDA sans télécharger à nouveau les brochures.

## Contenu

- `coverage.parquet` — couverture des 136 objets OFS et motifs d'exclusion ;
- `sources.parquet` — provenance des 48 brochures ;
- `pages.parquet` — 2 459 pages et méthode d'extraction ;
- `sections.parquet` — 137 sections reconstruites et champs textuels ;
- `section_links.parquet` — liens candidats section ↔ objet ;
- `votes_intermediate.parquet` — objets avant filtre ML ;
- `related_votes.parquet` — relations explicitement fournies par les sources ;
- `model.parquet` — lignes actuellement éligibles au modèle (vide tant que les revues humaines ne sont pas validées) ;
- `model_exclusions.parquet` — exclusions et raisons ;
- `document_audit.parquet`, `audit_report.md`, `correction_audit.json`, `source_provenance.json`, `swissvotes_join_audit.json` — audit et provenance.

Les **PDF bruts**, caches et le CSV Swissvotes source ne sont pas inclus. Le snapshot doit pouvoir être régénéré avec les scripts documentés dans `docs/datasets/federal_explanations/README.md`.

# Explications du Conseil fédéral

Ce dataset contient les textes et recommandations des brochures officielles de la Chancellerie fédérale. Il reste séparé des résultats OFS et de Swissvotes.

Le traitement ne lit pas Swissvotes et ne produit pas de dataset fusionné ni de `model.parquet`. Les identifiants OFS, dates et types de question servent uniquement à préparer et contrôler les correspondances. Les résultats communaux ne sont pas copiés dans les tables des brochures. Les liens candidats ne sont pas automatiquement validés.

## Scripts

Tous les modules sont dans `scripts/federal_explanations/` :

- `collect_federal_explanations.py` : collecte des PDF et de leur provenance.
- `audit_federal_explanations.py` : unique pipeline d'extraction et de préparation des correspondances.
- `federal_explanations_ocr.py`, `federal_explanations_layouts.py`, `federal_explanations_fields.py` : extraction du texte, découpage et lecture des champs officiels.
- `federal_explanations_corrections.py`, `federal_explanations_relations.py`, `federal_explanations_temporal.py` : corrections traçables, relations entre objets et contrôles temporels, y compris l'export de texte à la date de prévision.
- `build_federal_explanations_snapshot.py` : export des cinq tables propres à cette source.
- `federal_explanations_eda.py` : graphiques et rapport exploratoire.

La pipeline initiale et l'audit complet sont consolidés dans `audit_federal_explanations.py`. La seconde implémentation de la jointure Swissvotes a été supprimée ; les clés communes sont définies dans `scripts/common/vote_keys.py` et leurs contrôles dans `scripts/integration/prepare_join.py`.

## Snapshot versionné

Le dossier data/processed/federal_explanations contient cinq tables :

- objects.parquet : raccordement minimal aux vote_id OFS et statuts de validation
- sections.parquet : texte, résumés et recommandations extraits
- pages.parquet : texte page par page et méthode native/OCR
- sources.parquet : provenance des brochures
- section_links.parquet : liens candidats entre sections et vote_id

## Reproduction

Exécuter les commandes depuis la racine du dépôt. Préparer d'abord les données OFS avec `python -m scripts.run_pipeline`.

Collecter les brochures si elles ne sont pas encore disponibles :

```bash
python -m scripts.federal_explanations.collect_federal_explanations --ofs data/processed/ofs-votes/votes_communes.parquet --manifest data/raw/federal_explanations/sources.json --cache data/raw/federal_explanations/pdfs
```

Le manifeste doit référencer les PDF locaux et expliciter les validations humaines. La date de collecte ne prouve pas la disponibilité avant le vote.

Extraire les données et préparer les liens vers les objets OFS :

```bash
python -m scripts.federal_explanations.audit_federal_explanations --ofs data/processed/ofs-votes/votes_communes.parquet --sources data/raw/federal_explanations/sources.json --output data/interim/federal_explanations
```

Les sorties comprennent les sources, pages, sections, liens candidats, diagnostics de couverture, relations entre identifiants et `link_eligibility.parquet`. Ce dernier contient seulement les identifiants, leur admissibilité et les motifs d'exclusion.

Puis le snapshot propre est construit avec :

```bash
python -m scripts.federal_explanations.build_federal_explanations_snapshot --input data/interim/federal_explanations --output data/processed/federal_explanations
python -m scripts.federal_explanations.federal_explanations_eda --input-dir data/processed/federal_explanations --output-dir reports/generated/federal_explanations/eda
```

L'EDA se trouve dans notebooks/datasets/federal_explanations/eda.ipynb.

Le snapshot déjà versionné reste une extraction historique ; la réorganisation ne le régénère pas automatiquement. Pour migrer un ancien audit, utiliser un nouveau répertoire de sortie afin de ne pas confondre les anciens exports fusionnés avec les nouveaux diagnostics.

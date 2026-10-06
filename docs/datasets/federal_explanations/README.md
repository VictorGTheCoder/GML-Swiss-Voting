# Explications du Conseil fédéral

## Rôle dans le projet

Cette source fournit le contenu officiel disponible autour des objets de votation fédérale : texte explicatif, résumé officiel et recommandations des autorités lorsqu'elles peuvent être extraites sans ambiguïté.

Périmètre actuel : brochures françaises de la Chancellerie fédérale pour les votations 2011–2026. Swissvotes est utilisé comme source structurée complémentaire pour les métadonnées, mais le texte explicatif provient de la brochure officielle.

Le pipeline reste conservateur : une extraction technique réussie ne prouve ni la disponibilité pré-scrutin, ni le bon appariement à un objet OFS, ni la validité sémantique du texte.

## Structure des sorties

Le pipeline écrit ses données dans `data/processed/federal_explanations/` :

- `coverage.parquet` — une ligne par objet OFS attendu et les raisons d'exclusion ;
- `sources.parquet` — provenance des brochures ;
- `pages.parquet` — texte et méthode d'extraction par page ;
- `sections.parquet` — sections reconstruites et champs textuels ;
- `section_links.parquet` — liens candidats entre sections et objets OFS ;
- `related_votes.parquet` — relations entre objets uniquement lorsqu'elles sont fournies par la source ;
- `votes_intermediate.parquet` — objets avant filtrage ML ;
- `model.parquet` — sous-ensemble strictement éligible au modèle ;
- `model_exclusions.parquet` — exclusions et motifs ;
- `document_audit.parquet`, fichiers JSON et `audit_report.md` — contrôles et provenance détaillés.

Un **snapshot processed 2011–2026 est versionné dans Git** afin que toute l'équipe puisse utiliser immédiatement les données et exécuter l'EDA sans reconstruire les PDF. Les PDF bruts, le cache et le CSV source Swissvotes restent hors Git et permettent de reproduire ce snapshot.

Le rapport humain daté est conservé séparément dans `reports/datasets/federal_explanations/`.

## Collecte et reproduction

Utiliser le roster OFS local en lecture seule :

```bash
python scripts/collect_federal_explanations.py \
  --ofs data/processed/votes_communes.parquet \
  --manifest data/raw/federal_explanations_sources.json \
  --cache data/raw/federal_explanations_pdf_cache
```

Le collecteur parcourt l'archive officielle de la Chancellerie, télécharge les PDF français 2011–2026, vérifie leur signature, calcule leur SHA-256 et les place dans un cache local adressé par contenu. La date de collecte est une provenance technique et ne constitue jamais une preuve de publication pré-scrutin.

Télécharger ensuite le CSV Swissvotes dans le cache local, puis lancer l'audit complet :

```bash
python scripts/audit_federal_explanations_period.py \
  --ofs data/processed/votes_communes.parquet \
  --swissvotes data/raw/swissvotes.csv \
  --sources data/raw/federal_explanations_sources.json \
  --source-version 'DATASET CSV YYYY-MM-DD' \
  --output data/processed/federal_explanations
```

Une fois les sources mises en cache, le replay est hors ligne.

## Identifiants OFS et Swissvotes

Le numéro BFS Swissvotes `anr` est converti explicitement vers le `vote_id` OFS local avec :

```text
str(int(Decimal(anr) * 10))
```

Exemples : `554 → 5540`, `682.1 → 6821`.

Le mapping doit être unique et la date de votation doit correspondre. Les titres ne sont jamais utilisés comme jointure silencieuse. Les valeurs non convertibles, collisions, écarts de date et lignes hors période restent audités.

## Extraction PDF et OCR

Le pipeline tente d'abord l'extraction native page par page. L'OCR Tesseract est uniquement un fallback pour les pages sans texte natif exploitable.

Chaque page conserve notamment sa référence, sa méthode (`native` ou `ocr`), son statut technique et son statut sémantique. Une page OCR réussie reste `NOT_VALIDATED` jusqu'à revue.

Pour le fallback OCR, installer les bindings Python ainsi que Tesseract et les données françaises `fra`. Sans ces composants, le reste du pipeline continue à fonctionner et les pages concernées restent explicitement en échec.

## Reconstruction des sections

`scripts/federal_explanations_layouts.py` sépare la reconstruction de structure du reste du pipeline. Il reconnaît les headings modernes (`Objet N`) et un ensemble borné de formes plus anciennes (`Premier objet`, etc.).

Les layouts sont classés `MODERN`, `LEGACY`, `MIXED` ou `UNRECOGNIZED`. Les structures mixtes ou inconnues restent en revue ; aucune section n'est inventée.

Une différence entre le nombre de sections de brochure et le nombre de questions OFS n'est pas une erreur en soi : plusieurs questions peuvent partager une section et une question peut être liée à plusieurs sections.

## Corrections humaines

Les corrections sont versionnées par le SHA-256 exact de la source. Une décision n'est rejouée que si le hash courant correspond, qu'une justification est présente et qu'il n'existe pas de décision contradictoire pour le même champ.

Le fuzzy matching peut proposer des candidats (`PROPOSED` ou `AMBIGUOUS`) mais ne valide jamais automatiquement une correspondance OFS.

## Recommandations et objets liés

Le texte brut des recommandations du Conseil fédéral et du Parlement est conservé. Une cible normalisée n'est produite que lorsqu'une action et une proposition cible sont claires ; sinon la valeur reste nulle avec un motif explicite.

Les initiatives, contre-projets et questions subsidiaires restent des objets OFS distincts. Une même section peut être référencée par plusieurs objets. Les questions subsidiaires restent dans les exports intermédiaires mais sont exclues du dataset ML principal.

Aucune relation entre objets n'est inférée à partir d'une date commune ou du contenu de la brochure.

## Validation temporelle et éligibilité ML

La disponibilité d'une brochure est évaluée pour la version exacte du PDF. Les statuts sont :

- `CONFIRMED_PRE_VOTE` — preuve publique suffisante avant le scrutin ;
- `INVESTIGATE` — preuve insuffisante ou contradictoire ;
- `POST_VOTE` — publication ou modification pertinente établie après le scrutin.

Une ligne ne peut entrer dans `model.parquet` que si toutes les conditions sont remplies :

1. disponibilité pré-scrutin confirmée pour le hash courant ;
2. correspondance OFS explicitement validée ;
3. extraction et validation sémantique validées ;
4. objet non subsidiaire.

Un `model.parquet` vide est donc un résultat valide tant que les revues humaines n'ont pas été effectuées.

## EDA

L'EDA est présentée dans :

`notebooks/datasets/federal_explanations/eda.ipynb`

Le notebook réutilise `scripts/federal_explanations_eda.py` afin de garder une seule logique testable. Grâce au snapshot processed versionné, il peut être exécuté directement après un clone et l'installation de l'environnement.

Les figures générées vont dans `reports/generated/federal_explanations/eda/` et ne sont pas versionnées.

## Audit de référence

Le snapshot d'audit 2011–2026 est résumé dans :

`reports/datasets/federal_explanations/audit_2011_2026.md`

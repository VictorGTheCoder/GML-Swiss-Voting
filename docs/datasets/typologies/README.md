# OFS — Typologies territoriales et régions linguistiques

Contexte territorial et linguistique de chaque commune. Table statique (un seul millésime), distincte des résultats de votations.

## Source

Export Excel de la requête « Niveaux géographiques » de l'Application des communes suisses de l'OFS (`https://www.agvchapp.bfs.admin.ch/fr/typologies/query`). C'est un formulaire web, **pas une API documentée** : l'export peut changer sans préavis. Les pages du site OFS sur les typologies ne proposent que des PDF de méthodologie.

Le script envoie le formulaire (cookie de session, champs cachés `VersionDate` et `MinDate`), suit la redirection vers la page de résultats puis appelle le bouton XLSX. Niveaux demandés pour l'état au 01.01.2026 : `HR_GDETYP2020` (typologie des communes) et `HR_SPRGEB2020` (régions linguistiques). Les anciens millésimes (par exemple `HR_GDETYP2012`) sont refusés pour une date d'état de 2026 ; il faudrait une date dans leur période de validité.

## Scripts

Tous les modules sont dans `scripts/typologies/` :

- `download_typologies.py` : `data/raw/typologies/typologies_2026-01-01.xlsx` et `provenance.json`.
- `build_typology_features.py` : `data/processed/typologies/commune_typologies.parquet`.

## Contenu

2110 communes (celles du répertoire au 01.01.2026), sans valeur manquante ni doublon. Pour chaque commune : numéro et nom, canton, district, et quatre classifications avec code et libellé :

- `urban_rural` : typologie urbain-rural (3 classes : urbain 509, intermédiaire 580, rural 1021) ;
- `commune_type_9` et `commune_type_25` : typologie des communes en 9 et 25 types ;
- `language_region` : région linguistique (allemand 1374, français 606, italien 115, romanche 15).

L'export s'appelle « typologie 2020 », mais les nomenclatures sont celles de 2012 (`CL_STALAN`, `CL_GDET9`, `CL_GDET25`) et de 2011 (`CL_SPRGEB`).

## Disponibilité avant scrutin

La date de publication de cette classification n'a pas été établie. Elle est constante dans le temps et exprimée sur les communes de 2026. Pour les scrutins antérieurs à son millésime (2011–2012), son usage n'est pas admissible sans justification.

## Reproduction

```bash
python -m scripts.typologies.download_typologies
python -m scripts.typologies.build_typology_features
```

Dépend du snapshot 2026 de `scripts/repertoire_communes/` (contrôle de l'ensemble des communes).

# Répertoire historique et mutations des communes (OFS)

Source technique, pas une variable prédictive : elle sert à relier les codes communes des différentes sources (résultats de votations, STATPOP, typologies). Elle est distincte des résultats OFS et n'est jamais fusionnée avec eux.

## Source

API de l'Application des communes suisses de l'OFS (`https://www.agvchapp.bfs.admin.ch`), sans authentification :

- `/api/communes/snapshot?date=jj-mm-aaaa&useBfsCode=true` : communes valides à une date (tous niveaux : canton, district, commune).
- `/api/communes/mutations?includeTerritoryExchange=false&startPeriod=…&endPeriod=…` : une ligne par couple commune initiale → commune terminale de chaque mutation.

La date de fin des mutations ne peut pas être dans le futur (réponse 400).

## Scripts

Tous les modules sont dans `scripts/repertoire_communes/` :

- `download_repertoire.py` : snapshots au 01.01.2010 et au 01.01.2026, historique des mutations depuis 1960.
- `convert_repertoire_to_parquet.py` : conversion typée en Parquet (`data/interim/repertoire_communes/`).
- `commune_crosswalk.py` : suit un code commune d'une date à une autre à travers les mutations.
- `check_vote_codes.py` : compare les codes du cube des votations au répertoire à chaque date de scrutin.

## Fichiers

- `data/raw/repertoire_communes/` : CSV bruts, `provenance.json` (URL, date, taille, SHA-256) et `vote_snapshots/` (un snapshot par date de votation, créé par le contrôle des codes).
- `data/interim/repertoire_communes/commune_mutations.parquet` et `commune_snapshots.parquet`.
- `data/processed/repertoire_communes/crosswalk_<départ>_to_<cible>.csv` : correspondance, une ligne par couple (commune source, commune cible).
- `reports/datasets/repertoire_communes/vote_code_check.csv` : un contrôle par date de votation (généré localement, non versionné).

## Correspondance de codes

Un code à la date de départ est suivi à travers les mutations postérieures, jusqu'à la date cible incluse (un snapshot à la date D contient déjà les mutations datées D). Une fusion (n → 1) donne une cible. Une scission ou un échange de territoire (1 → n) donne plusieurs cibles **sans poids** : les poids doivent venir d'une variable de population et sont laissés à l'appelant.

Validation 2010 → 2026 : les 2596 communes de 2010 aboutissent chacune à une seule commune de 2026 (2012 inchangées, 584 recodées ou fusionnées), et les 2110 communes de 2026 ont au moins une source.

## Résultats de votations et répertoire

Le cube des votations n'utilise pas les codes valides à la date de chaque scrutin. Les premiers scrutins portent des codes plus récents : Zürich est 261 dans le cube en 1960, code attribué en 1990, alors que le répertoire de 1960 le nomme 253. Sur les 191 dates, entre 0 et 228 codes par date sont absents du répertoire à cette date, mais aucun n'est sans lien avec les communes du répertoire (écart de lignée : 0) et tous se rattachent à une commune de 2026.

Un contrôle ponctuel sur 390 fusions depuis 1975 montre que l'électorat du code survivant ne change pas à la date de fusion (rapport médian après/avant : 1,002) et que les codes absorbés n'ont pas de résultats avant. Le cube est donc rétro-agrégé sur une géographie unique, proche de celle de 2026. Une conversion de codes n'est pas nécessaire pour les votations ; elle l'est pour STATPOP (frontières 2025) et pour toute source datée.

Points à garder en tête :

- 2105 communes ont des résultats au dernier scrutin (14.06.2026) pour 2110 au répertoire. Cinq communes bernoises n'apparaissent jamais dans le cube : Meienried (389), Hellsau (408), Deisswil bei Münchenbuchsee (535), Oberhünigen (629) et Niedermuhlern (877). Hypothèse non vérifiée : elles sont déjà comptées dans leur commune d'accueil.
- Jusqu'en 1982, environ 1673 communes ont des résultats ; en 1960, aucune commune d'AG, FR ou TI.
- Les scissions antérieures à 2010 existent (Bolligen, 1983) et demandent des poids.

## Reproduction

Depuis la racine du dépôt :

```bash
python -m scripts.repertoire_communes.download_repertoire
python -m scripts.repertoire_communes.convert_repertoire_to_parquet
python -m scripts.repertoire_communes.commune_crosswalk --from 2010-01-01 --to 2026-01-01
python -m scripts.repertoire_communes.check_vote_codes
```

`check_vote_codes` nécessite le cube OFS interim (`python -m scripts.ofs_votes.parse_ofs_votes`). Il télécharge un snapshot par date de votation (environ 190) puis suit chaque code : compter une dizaine de minutes.

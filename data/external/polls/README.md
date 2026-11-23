# Sondages pré-vote SSR / gfs.bern

Capture du **23 novembre 2026** : **96 lignes, 48 objets et deux vagues par objet**.
Les 44 objets fédéraux de 2021 à 2025 sont couverts, ainsi que les quatre objets
du 29 novembre 2026. Les valeurs proviennent des tableaux numériques des
graphiques publiés par gfs.bern pour SSR. Aucune colonne de résultat populaire
n'est lue par le collecteur, y compris lors des correspondances avec Swissvotes.

## Fichiers et reproduction

- `srg_gfs_polls.csv` : une ligne par objet et vague, avec dates, modalités,
  correspondance Swissvotes et provenance.
- `source_evidence.json` : URLs des 32 pages, dates annoncées, titres des
  graphiques, tableaux nationaux exacts, métadonnées et empreintes SHA-256 des
  réponses sources. Les chiffres permettent une reproduction hors ligne.
- `reviewed_mappings.json` : correspondances revues entre date, titre exact du
  graphique et objet Swissvotes. Aucun rapprochement approximatif n'est utilisé
  au moment de l'extraction finale.
- `provenance.json` : couverture, contrôles, exclusions, avertissement sur les
  versions historiques et empreintes des artefacts.

Depuis la racine du dépôt :

```bash
.venv/bin/python scripts/modeling/collect_poll_features.py --include-vote-date 2026-11-29
.venv/bin/python scripts/modeling/collect_poll_features.py --offline --include-vote-date 2026-11-29
.venv/bin/python -m pytest tests/test_collect_poll_features.py -q
```

`--reuse-sources` conserve les sources déjà capturées et ne télécharge que les
pages ou graphiques manquants. Une actualisation complète sans cet argument
peut récupérer une nouvelle version des sources : conserver les artefacts
figés avec les expériences et prévisions qui les ont utilisés.

## Couverture vérifiée

| Période | Objets Swissvotes | Objets avec deux vagues | Lignes |
| --- | ---: | ---: | ---: |
| 2012–2015 | 41 | 0 | 0 |
| 2016–2020 | 42 | 0 | 0 |
| 2021 | 13 | 13 | 26 |
| 2022 | 11 | 11 | 22 |
| 2023 | 3 | 3 | 6 |
| 2024 | 12 | 12 | 24 |
| 2025 | 5 | 5 | 10 |
| 29 novembre 2026 uniquement | 4 | 4 | 8 |

Le sitemap officiel des publications pré-vote Cockpit commence en 2021.
Des articles SSR et anciens rapports pré-vote existent avant cette date, mais
une archive structurée, complète et datée n'a pas été récupérée dans cette
collecte. L'absence de données n'est pas remplacée par une valeur inventée.
Sur la population d'entraînement 2016–2022 de 66 objets, seuls 24 ont donc ces
sondages. Une évaluation comparative doit conserver sa population complète et
prévoir un modèle de repli pour les objets sans sondage.

## Schéma et règles temporelles

`vote_key` est l'identifiant Swissvotes sous forme de chaîne. Les colonnes
`yes_certain`, `yes_lean`, `undecided`, `no_lean`, `no_certain`, `yes_total` et
`no_total` sont exprimées sur **0 à 100**. Diviser par 100 pour les associer à
une cible communale sur 0 à 1. `yes_total` additionne les deux modalités oui;
`no_total` additionne les deux modalités non. Les indécis restent explicites.

Les sommes publiées des cinq catégories sont préservées : 93 lignes totalisent
100, deux totalisent 101 et une 99, à cause des valeurs arrondies affichées dans
les CSV. Le collecteur n'impose pas une normalisation silencieuse. Une
renormalisation éventuelle est une transformation à déclarer dans le modèle.

`survey_start`, `survey_end` et `survey_midpoint` viennent de la fiche
méthodologique de chaque page. `published_at` est la date et l'heure de
publication **annoncées**, avec le décalage de `Europe/Zurich`. Les tableaux
deux vagues sont sélectionnés par leur date explicite; les dates en colonnes
Datawrapper ne sont jamais assimilées à une colonne unique de pourcentages.

La deuxième vague de cette collecte est annoncée à J−11. Pour une prévision
à J−28, elle n'est donc pas disponible : sélectionner uniquement les lignes
dont `published_at` est antérieur ou égal à l'heure de la prévision. Un modèle
à J−11 et un modèle à J−28 répondent à deux objectifs différents.

Les sondages décrivent l'intention nationale déclarée parmi les personnes
ayant l'intention de participer. Ce sont des mesures d'opinion, pas les
résultats populaires ni une cible communale. Les variantes avec sondages
doivent conserver l'évaluation temporelle par nouveaux objets et les mêmes
communes/objets que leur comparaison sans sondages.

## Statut de la preuve historique

Les sources sont consultées dans leur version actuelle. Pour les 88 lignes
2021–2025, aucune archive datée de la version originelle n'a été vérifiée.
Toutes les lignes portent donc `historical_version_verified=false` et
`strict_forecast_ready=false`. Les dates annoncées constituent une information
utile, mais elles ne prouvent pas que les valeurs actuelles sont exactement
celles présentes à cette date.

Les graphiques Infogram exposent `createdAt` et `updatedAt`. Parmi leurs
48 lignes, **16 ont une date de modification au jour du vote ou après**. Cette
observation peut concerner la présentation; elle ne prouve pas un changement
des valeurs. Elle empêche néanmoins d'affirmer une disponibilité historique
exacte. Le CSV conserve ces dates et le drapeau
`chart_updated_on_or_after_vote_date`. Pour les 48 lignes Datawrapper, la
métadonnée de modification n'est pas fournie par le CSV : le champ reste vide.

Les huit lignes du 29 novembre 2026 ont été capturées le 23 novembre, avant
le vote, et portent `captured_before_vote=true`. Les vagues sont annoncées aux
23 octobre et 18 novembre 2026. Les empreintes de la présente capture peuvent
être conservées avec une prévision réellement figée avant le vote; les autres
conditions du pipeline strict restent à contrôler séparément.

## Sources primaires et contrôles

Découverte :
<https://cockpit.gfsbern.ch/de/wp-sitemap-posts-cpt_cockpit-1.xml>.
Seules les familles d'URL `srg_trend_*` et `trend_w1_*` / `trend_w2_*` sont
admises; le titre doit annoncer une première ou deuxième enquête SRG pré-vote.
Les années 2021–2025 et la date future demandée sont explicitement limitées.

Exemples de sources :

- [Deuxième vague du 7 mars 2021](https://cockpit.gfsbern.ch/de/cockpit/srg_trend_032021-2/),
  avec [tableau Infogram E-ID](https://e.infogram.com/_/14XeDo6lN9ZHKkLQ6qVd?src=embed).
- [Deuxième vague du 25 septembre 2022](https://cockpit.gfsbern.ch/de/cockpit/srg_trend_25092022_w2/).
- [Première vague du 28 septembre 2025](https://cockpit.gfsbern.ch/de/cockpit/trend_w1_28092025/),
  avec [CSV Datawrapper de la fiscalité des résidences secondaires](https://datawrapper.dwcdn.net/vRZlW/1/data.csv).
- [Deuxième vague du 29 novembre 2026](https://cockpit.gfsbern.ch/de/cockpit/trend_w2_29112026-2/).

Le collecteur exclut les sous-échantillons régionaux/partisans et les
graphiques d'arguments. Dix graphiques d'arguments de juin 2021, dont les titres
techniques ne les distinguent pas tous des sondages, sont consignés parmi les
graphiques rejetés faute de distribution nationale à cinq modalités. Ils ne
créent aucune ligne du CSV.

Les contrôles vérifient les intervalles de dates, les pourcentages, l'unicité
objet/vague, la correspondance date/titre/identifiant, la distinction entre
vagues et l'exclusion des sous-groupes. **12 tests passent**. Les fichiers de
prétraitement et les modèles V2 existants ne sont pas modifiés par ce
collecteur.

# Données de base : résultats communaux des votations fédérales (OFS)

Socle du pipeline de données : récupération, audit, nettoyage et validation des résultats
historiques des votations fédérales au niveau communal. Unité finale : **commune × objet de votation**.

Les chiffres détaillés sont dans les rapports **générés automatiquement** (à ne pas éditer à la main) :

- `reports/data_audit.md` : audit du cube brut, avant nettoyage ;
- `reports/cleaning_log.md` : lignes supprimées à chaque étape, avec la raison ;
- `reports/validation_report.md` : résultat de chaque contrôle automatique.

## 1. Reconstruire le dataset

```bash
conda env update -f environment.yml --prune
conda activate swiss-votes-ml
python scripts/build_dataset.py            # télécharge si data/raw est vide, puis audit -> nettoyage -> validation
python scripts/build_dataset.py --force-download   # re-télécharge la dernière version OFS
python -m pytest                           # tests unitaires (sans réseau, sur un mini-cube synthétique)
```

Durée d'environ 20 s hors téléchargement (53 Mo), pic mémoire d'environ 1,4 Go.
Les étapes peuvent aussi être lancées séparément, dans cet ordre :
`download_votes.py` → `parse_votes.py` → `audit_votes.py` → `clean_votes.py` → `validate_votes.py`.

| Script | Rôle | Sortie |
|---|---|---|
| `scripts/votes_config.py` | chemins, identifiants OFS, correspondance des mesures | – |
| `scripts/download_votes.py` | téléchargement du cube PX + fiche de provenance ; ne remplace jamais un fichier existant sans `--force` | `data/raw/px-x-1703030000_101.px`, `…provenance.json` |
| `scripts/parse_votes.py` | lecture PX → table longue **sans perte** (tous niveaux, toutes cellules) | `data/interim/votes_all_levels.parquet` |
| `scripts/audit_votes.py` | audit du brut | `reports/data_audit.md` |
| `scripts/clean_votes.py` | niveau commune, `yes_share`, flags ; chaque suppression est journalisée | `data/interim/votes_communes_clean.parquet`, `reports/cleaning_log.md` |
| `scripts/validate_votes.py` | contrôles ; un contrôle `error` en échec **bloque** l'écriture du processed | `reports/validation_report.md`, `data/processed/votes_communes.parquet` |
| `scripts/build_dataset.py` | orchestre tout ce qui précède | – |
| `notebooks/01_data_audit.ipynb` | exploration visuelle uniquement ; le pipeline n'en dépend pas | – |

`data/raw`, `data/interim` et `data/processed` ne sont pas versionnés : tout se reconstruit
depuis l'OFS. Le fichier brut n'est jamais modifié.

## 2. Provenance

| | |
|---|---|
| Source | Office fédéral de la statistique (OFS), Statistique des votations et des élections |
| Dataset | *Votations populaires (résultats au niveau des communes depuis 1960)* |
| Identifiant OFS | `px-x-1703030000_101` |
| Page officielle | https://www.bfs.admin.ch/asset/fr/px-x-1703030000_101 |
| Endpoint utilisé | `https://www.pxweb.bfs.admin.ch/DownloadFile.aspx?file=px-x-1703030000_101` (cube complet, GET) |
| Format original | PC-Axis `.px`, bilingue DE/FR ; l'en-tête annonce `CODEPAGE="iso-8859-15"` mais le fichier est en **UTF-8 avec BOM** |
| Version récupérée | `LAST-UPDATED="20260821 08:30"`, 53 376 455 octets, SHA-256 `e66550d4…8d80` |
| Date de récupération | 2026-09-29 (horodatage exact dans `data/raw/px-x-1703030000_101.provenance.json`) |
| Période | 1960-05-29 → 2026-06-14 : 511 objets, 191 dates |
| Options de requête | aucune : cube complet (7 mesures × 2 363 lieux × 511 objets) |

Pourquoi cet endpoint :
- l'API JSON PXWeb (`/api/v1/fr/px-x-1703030000_101/...`) fonctionne pour les métadonnées, mais le pare-feu OFS
  rejette une requête POST de cette taille (environ 8,5 millions de valeurs) ;
- l'URL DAM (`dam-api.bfs.admin.ch/hub/api/dam/assets/<n°>/master`) change de numéro à chaque mise à jour,
  alors que `DownloadFile.aspx?file=<id>` reste stable.

Le fichier servi est identique, octet pour octet, à celui obtenu via le DAM.

Le cube est **vivant**. L'OFS y ajoute chaque scrutin et marque certains résultats comme provisoires
(à la date de récupération : novembre 2025, mars et juin 2026, colonne `is_provisional`). Un
`--force-download` ultérieur peut donc produire des chiffres légèrement différents. La fiche de
provenance (SHA-256, `LAST-UPDATED`) permet de savoir quelle version a servi.

## 3. Structure du cube et unité d'observation

Le cube a trois dimensions : **lieu** (Suisse → canton → district → commune, liste hiérarchique ordonnée) ×
**objet** (code OFS + libellé `AAAA-MM-JJ Titre`) × **mesure** (7 valeurs). Chaque cellule lieu × objet devient une
ligne et chaque mesure une colonne. Au niveau commune, une ligne correspond donc déjà à **commune × objet** : aucun autre pivot n'est nécessaire.

Signification des mesures (lue dans les libellés `VALUES` / `VALUES[fr]` du PX) :

| code | DE | FR | colonne projet |
|---|---|---|---|
| 1 | Stimmberechtigte | Electeurs inscrits | `eligible_voters` |
| 2 | Abgegebene Stimmen | Bulletins rentrés | `ballots_cast` |
| 3 | Beteiligung in % | Participation en % | `turnout_pct_ofs` |
| 4 | Gültige Stimmzettel | Bulletins valables | `valid_ballots` |
| 5 | Ja | Oui | `votes_yes` |
| 6 | Nein | Non | `votes_no` |
| 7 | Ja in % | Oui en % | `yes_pct_ofs` |

Il n'y a **pas** de colonnes « blancs » et « nuls » séparées. On ne peut dériver que
`blank_invalid_ballots = ballots_cast - valid_ballots`, blancs et nuls confondus.

## 4. Dataset processed : `data/processed/votes_communes.parquet`

1 025 903 lignes (2 105 communes + 26 unités spéciales × 511 objets, là où un résultat existe).
Clé unique : `(vote_id, municipality_id)`, vérifiée automatiquement.

| colonne | description |
|---|---|
| `vote_id` | code OFS de l'objet (une question ; plusieurs objets par date) |
| `vote_date` | date du scrutin (tirée du libellé) |
| `vote_title_fr`, `vote_title_de` | titre officiel |
| `is_tiebreak_question` | question subsidiaire (voir §5) |
| `is_provisional` | résultat provisoire selon la note OFS |
| `municipality_id` | numéro OFS de commune, 4 chiffres sous forme de texte (`"0001"`), état au 01.01.2026 |
| `municipality_name`, `municipality_name_de` | nom de la commune |
| `canton`, `district_id`, `district_name` | canton (abréviation) et district OFS (`00` + n° de district) |
| `is_special_unit` | unité spéciale ≥ 9000 (Suisses de l'étranger, etc.) : **ce n'est pas une commune** |
| `eligible_voters`, `ballots_cast`, `valid_ballots`, `votes_yes`, `votes_no` | comptes OFS (entiers, NA si absents) |
| `blank_invalid_ballots` | `ballots_cast - valid_ballots` |
| `yes_share` | **target** : `votes_yes / (votes_yes + votes_no)` |
| `turnout` | `ballots_cast / eligible_voters` |
| `yes_pct_ofs`, `turnout_pct_ofs` | pourcentages publiés par l'OFS (utilisés pour vérifier les recalculs) |
| `flag_valid_gt_ballots`, `flag_yes_no_gt_valid` | incohérences OFS conservées et signalées |

**Pour un modèle commune × votation, filtrer au minimum** `~is_special_unit & ~is_tiebreak_question`.

## 5. Particularités et problèmes identifiés

1. **Fusions de communes (harmonisation).** Note OFS : *« Résultats harmonisés, communes au 01.01.2026 […].
   L'harmonisation concerne uniquement la répartition des résultats entre les communes et les districts ; les
   totaux cantonaux et suisse restent inchangés et correspondent à l'état original. »* Ce que l'on vérifie dans les données :
   - les résultats des anciennes communes sont réattribués à la commune actuelle. Glarus Nord (fusion 2011),
     Val-de-Ruz (2013) et Stammheim (2019) ont chacune une série complète depuis 1960, et les anciennes communes
     n'existent plus comme unités. Les résultats sur les frontières historiques ne sont pas disponibles ;
   - la somme des communes d'un canton ≠ la ligne canton lorsqu'une commune a changé de canton :
     Moutier BE → JU (écarts miroirs BE/JU sur 385 objets entre 1981 et 2025), Laufental BE → BL (102 objets
     avant 1994), communes jurassiennes avant 1979. Les agrégats cantonaux doivent être **calculés à partir des
     lignes communales**, sans les mélanger avec les lignes canton de l'OFS ;
   - les scissions ne sont pas rétropolées. 16 communes n'ont des données qu'après 1981 (Ittigen et
     Ostermundigen, séparées de Bolligen en 1983). Pour les autres, la raison probable est une ancienne urne
     commune, ce qui n'a pas été vérifié cas par cas.

   Audit détaillé de compatibilité avec STATPOP et les élections : `docs/geography_compatibility_audit.md`.
   Conséquence : pour joindre des caractéristiques communales, il faut qu'elles soient exprimées dans
   **l'état communal 2026** (ou les convertir avec la table de mutations OFS). Rien n'est reconstruit ici.
   C'est une réponse partielle à la question 3 de `docs/communal_features_audit.md` (§9).
2. **Données 1960-1980 incomplètes** (base sotomo). AG, FR et TI n'ont de données communales que pour 2 des
   118 objets de cette période (suffrage féminin 1971-02-07, « solution du délai » 1977-09-25). La couverture passe d'environ 1 670 à environ 2 090 communes en 1981.
3. **Unités spéciales** (codes ≥ 9000 : `ZH-Ausland-CH`, `TI-voto per corrispondenza`, `GE-autres`, …). 41 codes,
   dont 26 ont des résultats. Ce sont des votes non attribués à une commune. Ils sont conservés et marqués `is_special_unit`.
4. **Communes à urne commune** (Meienried, Hellsau, Deisswil b. M., Oberhünigen, Niedermuhlern). Elles n'ont jamais
   de résultat propre, car elles sont dépouillées avec une autre commune. Elles sont supprimées à l'étape `drop_empty_cells`.
   Cela répond, avec le point 3, à la question 10 de `docs/communal_features_audit.md` (§9).
5. **Questions subsidiaires** (4 objets : 2000, 2002, 2010, 2026). *Oui = pour l'initiative, non = pour le
   contre-projet* : `yes_share` n'y est pas une part d'approbation (`is_tiebreak_question`).
6. **`yes + no < valid_ballots`** (49 729 lignes). C'est structurel aux dates où un même bulletin porte initiative,
   contre-projet et question subsidiaire : une question peut rester blanche. Ce n'est pas une erreur.
7. **Incohérences OFS conservées et signalées** : 81 lignes `yes + no > valid_ballots` (1972 et 1974) et
   4 lignes `valid_ballots > ballots_cast` (Clos du Doubs, 1978-12-03). Elles n'affectent pas `yes_share`,
   qui reste dans [0, 1].
8. **Valeurs manquantes.** `"..."` = chiffre inconnu. 9 218 lignes ont oui et non mais pas d'inscrits ou de bulletins
   rentrés : `yes_share` est valide, `turnout` vaut NA.
9. **Suppressions** (détail dans `reports/cleaning_log.md`) : lignes agrégées canton/district/Suisse (conservées dans
   `interim`), 73 254 cellules vides de la grille, 3 lignes sans oui/non, 1 ligne avec oui + non = 0.
10. **Divers.** La note OFS indique « Stand der Datenbank: August 2025 » en allemand et « août 2026 » en français.
    Le recalcul de `yes_share` et de `turnout` concorde avec les pourcentages OFS à 5·10⁻⁸ près.

## 6. Contrôles automatiques

Contrôles bloquants (`error`) : identifiants et target non vides ; unicité `vote_id × municipality_id` ; date dans
[1960-01-01, aujourd'hui] ; une date par objet ; un nom et un canton par commune ; comptes ≥ 0 ; `yes_share` dans [0, 1] ;
`yes_share` et `turnout` égaux aux pourcentages OFS (tolérance 1e-6 point) ; `ballots_cast ≤ eligible_voters`.

Avertissements (conservés et signalés) : `valid_ballots ≤ ballots_cast`, `yes + no ≤ valid_ballots`,
disponibilité de la participation, `yes + no = valid_ballots`.

La somme des communes comparée aux totaux cantonaux ne peut pas servir de contrôle bloquant, à cause de
l'harmonisation (§5.1). Elle est documentée dans l'audit (section 9).

## 7. Questions ouvertes

- Faut-il restreindre le périmètre de modélisation à la période ≥ 1981 (couverture complète), voire plus récente ?
- Les caractéristiques communales futures sont-elles disponibles dans l'état communal 2026, ou faut-il utiliser la
  table de mutations OFS ?
- Faut-il exclure les résultats provisoires tant que l'OFS ne les a pas définitivement validés ?
- Traitement des communes à historique court (scissions, anciennes urnes communes) dans les features historiques.

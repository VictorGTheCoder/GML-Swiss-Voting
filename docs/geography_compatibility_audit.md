# Audit de compatibilité géographique : votations × STATPOP × élections

**Question.** Pour une ligne `commune × votation`, les caractéristiques démographiques (STATPOP) et politiques
(élections au Conseil national) jointes représentent-elles le **même territoire** que le résultat de vote ?

**Réponse courte.** Oui pour environ 98 % des lignes 2013–2024, à condition de ne **pas** joindre naïvement sur
le numéro OFS. Les trois sources sont toutes harmonisées rétroactivement, mais à **trois états communaux
différents**. Il faut convertir chaque source vers l'état du dataset de votation (01.01.2026) avec la table des
mutations du répertoire officiel. C'est peu coûteux : 28 communes à convertir, et l'agrégation est exacte pour les
fusions. La règle à implémenter est au §7.

Chiffres et tableaux détaillés : `reports/geography_audit.md`, généré par
`python scripts/audit_municipality_geography.py`. Les sources sont mises en cache dans `data/raw/geography/`, avec leur provenance (URL, `LAST-UPDATED` OFS, date, SHA-256) en section 0 du rapport.

## 1. État communal de chaque source

Formulations exactes des notes OFS (`NOTE[fr]` des cubes PX) :

| Source | Cube | Formulation OFS | État vérifié |
|---|---|---|---|
| Votations | `px-x-1703030000_101` | « Résultats harmonisés, communes au 01.01.2026, y c. communes spéciales de la statistique politique […]. L'harmonisation concerne uniquement la répartition des résultats entre les communes et les districts ; les totaux cantonaux et suisse restent inchangés et correspondent à l'état original. » | 01.01.2026 |
| STATPOP | `px-x-0102010000_101` | « Jour de référence: 31 décembre. Référence spatiale: communes / 06.04.2025 » | 06.04.2025, **pour toutes les années 2010–2025** |
| Élections CN | `px-x-1702020000_105` (partis), `_101` (électeurs) | « Référence spatiale: communes au 01.07.2023, y c. communes spéciales […]. Afin que les résultats des élections au niveau communal soient plus faciles à comparer dans le temps, l'état des communes a été harmonisé à un certain moment. » | 01.07.2023, pour toutes les élections 1971–2023 |

« Vérifié » signifie que l'ensemble des numéros de commune de la source est **identique** à celui d'un snapshot
du répertoire officiel des communes (API `agvchapp.bfs.admin.ch`) à cette date. Aucune autre date testée ne
correspond (§1 du rapport généré).

Ce que l'OFS ne documente pas : la méthode exacte de redistribution (scissions, échanges partiels de territoire).
Aucune documentation publique n'a été trouvée. Le comportement a donc été établi **empiriquement** (§3–4).

## 2. Méthode de contrôle numérique

On compare des effectifs presque identiques par construction dans les trois sources :

- votes : `eligible_voters`, les électeurs inscrits au scrutin (dernier scrutin de l'année) ;
- STATPOP : Suisses de 18 ans et plus au 31.12 (total moins les âges 0 à 17) ;
- élections : électeurs inscrits à l'élection.

Sur le **même territoire**, le rapport votes/STATPOP est stable (≈ 1 ; il dépasse légèrement 1 dans les cantons qui
inscrivent les Suisses de l'étranger dans leur commune). Un **territoire différent** produit un décalage
persistant ou un saut l'année de la mutation. Une valeur **absente** avant la création de la commune signale le cas B.

Référence, sur 1 992 communes non signalées : écart médian de 0,37 % à la médiane cantonale, saut maximal annuel
médian de 2,2 %.

## 3. Tableau d'audit des cas

Valeurs : électeurs votes / Suisses 18+ STATPOP / électeurs élections (élection ≤ année). « Liés » : somme des
anciens numéros ou partenaires. Géographie : V = 01.01.2026, S = 06.04.2025, E = 01.07.2023.

| Commune (code V) | Mutation | Années testées | Votations | STATPOP | Élections | Même territoire ? | Problème / règle |
|---|---|---|---|---|---|---|---|
| Aeugst am Albis (0001) | aucune (contrôle) | 2013, 2024 | 1 375 → 1 370 | 1 358 → 1 373 (ratio 1,01 → 1,00) | 1 337 → 1 384 | Oui | – |
| Lausanne (5586) | aucune (contrôle) | 2013, 2024 | 63 310 → 67 900 | ratio 0,997 → 0,994 | 63 310 → 67 700 | Oui | – |
| Glarus Nord (1630) | fusion de 8 communes, 2011, nouveau code | 2010–2013, 2024 | présente dès 1960 | **présente en 2010** (avant création), ratio 1,012 → 1,004 → 1,011 | présente en 2011 | Oui (cas A partout) | – |
| Val-de-Ruz (6487) | fusion de 15 communes, 2013 | 2012–2014, 2024 | présente | présente en 2012, ratio 1,02–1,03 stable | **élection 2011 présente** (avant fusion) : 10 560 vs votes 10 670 | Oui (A) | – |
| Stammheim (0292) | fusion de 3 communes, 2019 | 2013, 2018–2020, 2024 | présente | ratio 0,998 → 0,995 → 0,998 (pas de saut) | 2015 présente : 2 003 vs 2 033 | Oui (A) | – |
| Verzasca (5399) | fusion + **transfert partiel** depuis Lavertezzo et Cugnasco-Gerra, 18.10.2020 | 2013, 2019–2021, 2024 | **saut** 627 → 726 en 2020 | stable (663 → 658) | 619 (2019) → 702 (2023) | **Non avant 2020** | votes et élections gardent l'ancien territoire, STATPOP est rétropolé : exclure avant le 18.10.2020 |
| Lavertezzo (5112), Cugnasco-Gerra (5138) | cèdent du territoire, 2020 | idem | saut de −9,7 % (5112) | stable | – | Non avant 2020 | idem |
| Klosters (3871) | changement de nom seul, 2021 | 2013, 2020–2022, 2024 | code inchangé | ratio 1,027–1,029 stable | idem | Oui | le nom n'est pas une clé |
| Murten (2275) | absorbe Clavaleyres (BE → FR), 2022 | 2013, 2021–2024 | présente | ratio 0,99 → 1,005 | 6 316 → 6 317 | Oui (effet < 1 %) | Clavaleyres ≈ 40 électeurs, indétectable |
| Kloten (0062) / Nürensdorf (0064) | échange partiel de territoire, 2024 | 2013, 2023–2025 | – | ratio 1,00–1,02 stable | somme votes/élections 0,99–1,01 | Oui (négligeable) | – |
| Baden (4021) | absorbe Turgi, 2024, **garde son code** | 2013, 2023–2025 | 13 820 (2023) | 14 000, ratio 0,99 (déjà fusionnée) | **Baden seule : 12 350** ; + Turgi 1 563 = 13 913 | S : oui ; **E : non avec le même code** | sommer 4021 + 4042 dans les élections |
| Basse-Vendline (6812) | fusion, 2024, nouveau code | 2013, 2023–2025 | 730 | présente (fusionnée), ratio 1,1–1,29 (JU : Suisses de l'étranger) | absente ; somme 6773 + 6775 = 734 | S : oui ; E : via somme | nouveau code, sinon NaN |
| Laténa (6513) | fusion de 4 communes, 2025 | 2013, 2024–2025 | 7 354 (2023) | présente dès 2010 : 7 082 (2023) | somme de 4 codes = 7 359 | S : oui ; E : via somme | – |
| Lema (5395) | fusion de 5 communes, 06.04.2025 | 2013, 2024–2025 | 2 127 | présente dès 2010 | somme = 2 129 | S : oui ; E : via somme | une fusion à la date même de l'état STATPOP y est déjà intégrée |
| Brugg (4095) | absorbe Villnachern, 01.01.2026, **garde son code** | 2013, 2024–2025 | 8 816 (2023) | **Brugg seule : 7 647** (ratio 1,15) ; + 4122 : ratio 1,00 | 7 707 ; + 4122 = 8 835 | **Non avec le même code** (S et E) | piège : même numéro, territoire différent |
| Fétigny-Ménières (2056) | fusion, 01.01.2026, nouveau code | 2013, 2024–2025 | 1 081 (2023) | absente ; 2016 + 2027 = 1 067 | absente ; somme = 1 081 | via somme | – |
| Moutier (6831) | BE → JU, **numéro 0700 → 6831**, 01.01.2026 | 2013, 2024–2025 | 4 522 (2023) | absente sous 6831 ; 0700 = 4 360 | 0700 = 4 504 | via table de numéros | forces des partis : listes bernoises jusqu'en 2023 |
| Laufen (2787) | changement de canton BE → BL (1994) | 2013, 2024 | présente | ratio 1,01–1,02 | présente | Oui | hors période |
| Ittigen (0362) | scission de Bolligen (1983) | 2013, 2024 | présente | ratio 1,01–1,02 | présente | Oui | hors période |
| Jaberg (0868) / Kirchdorf (0872) | Jaberg dépouillé à Kirchdorf jusqu'à fin 2017 | 2013, 2017–2019, 2024 | Jaberg absente avant 2018 | Jaberg présente dès 2010 | Jaberg absente en 2015 | **Kirchdorf avant 2018 = Kirchdorf + Jaberg** | sommer STATPOP 0872 + 0868 avant 2018 |
| Urnes communes actuelles (Meienried → Büren a.A., Hellsau → Höchstetten, Deisswil → Wiggiswil, Oberhünigen → Zäziwil, Niedermuhlern → Wald BE) | pas de bureau de vote | 2015, 2023 | commune silencieuse vide ; l'hôte compte les deux | les deux communes séparées ; ratio hôte seul 1,03–2,11, hôte + silencieuse 1,00–1,10 | idem votes | **Non avec le même code** | sommer hôte + silencieuse (Zäziwil = 0628 ; la note OFS indique à tort 629) |
| ZH-Ausland-CH (9010) | unité spéciale | 2013, 2024 | présente dès 2014 | absente | présente | Non applicable | exclure (`is_special_unit`) |

## 4. Enseignements par type de mutation

- **Fusion avant l'état de la source** (Glarus Nord, Val-de-Ruz, Stammheim, 151 communes issues de fusions
  2013–2024) : **cas A dans les trois sources**. La valeur historique est la reconstruction du territoire actuel. Ces
  communes sont même plus stables que la moyenne (saut médian 1,7 % contre 2,3 %). Les 7 signalées sont toutes
  expliquées : urne commune, transfert de 2020, Suisses de l'étranger en JU/GR/TI, Brugg.
- **Fusion après l'état de la source** : la source publie les anciennes communes. La somme des anciennes communes
  reproduit la valeur du dataset de vote (ratio 0,98–1,03 sur 28 communes × 3 années, §6 du rapport). Cela prouve
  aussi que la reconstruction des votes est une **somme des prédécesseurs** (cas A), et que la STATPOP rétropolée
  concorde avec la somme des élections pour les fusions 2024–2025 (par exemple Chur, Laténa).
- **Fusion avec conservation du numéro** (Brugg, Gurmels, Kriegstetten, Baden, Chur, Root, Rue, Ursy, …) : **piège
  silencieux**. La jointure réussit mais sur un territoire plus petit, avec un écart de 5 % à ×2,3 (Kriegstetten).
  L'égalité des numéros ne prouve pas l'égalité géographique.
- **Changement de numéro** (Moutier) : la jointure donne NaN, ce qui est visible mais fait perdre la commune sans
  table de correspondance.
- **Changement de nom seul** : aucun effet, le numéro est conservé.
- **Changement de canton** : le territoire est cohérent, mais les listes de partis et le nombre de sièges diffèrent
  (note OFS : les *suffrages* ne sont pas comparables, les *forces* le sont via le code national de parti). Le canton
  d'une ligne de vote est celui de 2026 (Moutier en JU pour tout l'historique).
- **Échange partiel de territoire entre communes survivantes** (5 mutations 2013–2025) : c'est le seul cas où
  votes et élections ne sont **pas** rétropolés alors que STATPOP l'est (cas C). Il est significatif seulement pour
  Verzasca, Lavertezzo et Cugnasco-Gerra (2020) ; les autres sont indétectables (< 2 %).
- **Scissions** : aucune en 2013–2024. Avant, elles ne sont pas rétropolées (Ittigen et Ostermundigen depuis 1983).
- **Urne commune** : le résultat de la commune silencieuse est dans la ligne de l'hôte, dans les votes comme dans
  les élections. STATPOP publie les deux séparément.
- **Unités spéciales** (Suisses de l'étranger, etc.) : absentes de STATPOP par nature.

Constat hors géographie, trouvé en passant : environ 90 communes (surtout VD) présentent des pics ponctuels
d'électeurs inscrits sur une seule date de vote, qui reviennent à la normale l'année suivante (par exemple Lavigny
×2,5 le 2016-11-27). Ce ne sont pas des mutations : seulement 3 pics sur 154 coïncident avec le répertoire. Ils
n'affectent pas `yes_share`, mais une feature de participation devrait les traiter avec prudence.

## 5. Compatibilité par source

| Source | Verdict | Condition |
|---|---|---|
| Votations (référence) | – | état 01.01.2026 ; cas A pour les fusions ; échanges partiels non rétropolés |
| STATPOP | **Compatible sous conditions** | convertir 06.04.2025 → 01.01.2026 : 1 changement de numéro et 4 fusions (dont 3 avec numéro conservé) ; sommer les urnes communes ; exclure les échanges partiels significatifs avant leur date |
| Élections CN | **Compatible sous conditions** | convertir 01.07.2023 → 01.01.2026 : 23 codes de vote touchés, dont 19 fusions ou changements de numéro et 4 échanges partiels négligeables ; sommer les *suffrages* des partis puis recalculer les forces (identité vérifiée sur 276 000 lignes, écart ≤ 0,2 pt sur 4 lignes) ; mêmes règles urnes et échanges |
| Typologies, régions linguistiques | Inconnue (non testée) | chaque version a son propre état communal : appliquer le même contrôle d'état (§7, étape 1) avant usage |

## 6. Impact quantitatif (2013–2024)

232 730 lignes et 2 117 unités (hors questions subsidiaires).

| Groupe | Communes | Lignes | Part des lignes | Traitement proposé |
|---|---:|---:|---:|---|
| A. Unités spéciales | 12 | 1 300 | 0,56 % | exclure |
| B. Mutées après l'état STATPOP | 5 | 550 | 0,24 % | convertir |
| C. Mutées après l'état élections | 23 | 2 530 | 1,09 % | convertir |
| D. Hôtes d'une urne commune | 5 | 550 | 0,24 % | sommer hôte + silencieuse |
| E. Échanges partiels de territoire | 11 | 1 210 | 0,52 % | exclure seulement Verzasca, Lavertezzo et Cugnasco-Gerra avant le 18.10.2020 (207 lignes) |
| Kirchdorf avant 2018 (urne Jaberg) | 1 | 49 | 0,02 % | sommer 0872 + 0868 |
| **Union A–E** | **47** | **5 150** | **2,2 %** | |

Avec la stratégie recommandée, on **n'exclut que ≈ 1 500 lignes (0,65 %)**, les unités spéciales et le transfert
Verzasca. Tout le reste est converti exactement.

## 7. Stratégies

| | A — géographie harmonisée (état des votes) | B — géographie historique | C — exclusions seules |
|---|---|---|---|
| Faisabilité | Élevée : les trois sources sont déjà harmonisées à un état récent ; il ne reste que les mutations entre 2023 et 2026 | Très faible : le cube de votes ne publie pas les anciennes communes ; il faudrait des données cantonales ou brutes par scrutin et des règles de répartition | Triviale |
| Exactitude | Exacte pour fusions, changements de numéro et urnes (vérifié, ratio ≈ 1,00) ; approximative pour 5 échanges partiels | Théoriquement maximale | Exacte sur le reste |
| Coût | Faible : une table de correspondance dérivée de l'API mutations et une agrégation par somme | Très élevé | Nul |
| Perte | ≈ 0,65 % des lignes | – | 2,2 % des lignes, dont des grandes communes (Baden, Chur, Brugg) |
| Risque | Erreur de mapping si l'état d'une source change lors d'une mise à jour OFS : à couvrir par un contrôle automatique | Élevé | Faible, mais biais : communes fusionnées récemment surreprésentées dans les exclusions |

## 8. Décision adoptée : règle d'architecture à implémenter

> **Adoptée le 2026-09-29 comme règle d'architecture du projet.** Les caractéristiques communales sont ramenées
> à la géographie du dataset des votations OFS (état communal au 01.01.2026) avant la jointure. Les grandeurs
> additives sont agrégées par somme, et les ratios ou pourcentages sont recalculés depuis leurs composantes,
> jamais moyennés directement. Les exceptions et contrôles ci-dessous (étapes 3, 5 et 6) font partie de la règle.

**Géographie de référence : l'état communal du dataset de votation (01.01.2026, `municipality_id`).**
Toute feature communale est ramenée dans cet état **avant** la jointure :

1. **Vérifier l'état de la source** : son ensemble de numéros doit être égal au snapshot du répertoire à sa date de
   référence (déclarée dans la note OFS). Sinon, arrêt. Une mise à jour OFS peut déplacer cette date : le contrôle
   le détecte.
2. **Table de correspondance** `source_code → municipality_id`, construite depuis l'API
   `/api/communes/mutations` pour les mutations *strictement postérieures* à l'état de la source et jusqu'au
   01.01.2026 : fusions n→1 (y compris l'absorbante qui garde son code), changements de numéro 1→1. L'identité
   s'applique partout ailleurs. On ignore les changements de nom et de district sans changement de numéro.
3. **Urnes communes** : ajouter à la table les communes silencieuses vers leur hôte (0389→0383, 0408→0410,
   0535→0553, 0629→0628, 0877→0888), ainsi que Jaberg 0868→0872 pour les années ≤ 2017.
4. **Agréger** en sommant les grandeurs additives (population, groupes d'âge, suffrages de parti, électeurs). Les
   parts et taux sont **recalculés** depuis les sommes, jamais moyennés. Pour la force des partis : suffrages
   sommés divisés par le total des suffrages sommés.
5. **Exclure**, avec un flag conservé dans le dataset : `is_special_unit` ; Verzasca (5399), Lavertezzo (5112)
   et Cugnasco-Gerra (5138) pour les scrutins antérieurs au 18.10.2020.
6. **Contrôle de non-régression** dans le pipeline de features : rapport `eligible_voters / Suisses 18+` par
   commune. Échec si un écart persistant dépasse 8 % à la médiane cantonale, hors liste documentée (cantons qui
   inscrivent les Suisses de l'étranger dans les communes). Ce contrôle aurait détecté automatiquement Brugg,
   Gurmels, Kriegstetten et les urnes communes.

Cette règle est compatible avec la contrainte ex ante de `docs/communal_features_audit.md` : elle traite *où*,
pas *quand*. La jointure temporelle (millésime STATPOP disponible avant le scrutin, élection strictement
antérieure) s'applique ensuite, sur des données déjà exprimées dans la géographie de référence.

## 9. Questions ouvertes

- **Stabilité de l'état des sources.** Chaque mise à jour OFS peut rebaser l'harmonisation (le cube des votes
  passera à 2027 ; STATPOP change à chaque millésime). La règle doit donc être recalculée à chaque
  `--force-download`. L'étape 1 le garantit, mais il faut l'implémenter.
- **Méthode OFS pour les échanges partiels** : documentation introuvable. Le comportement est déduit de 5 cas,
  dont un seul est mesurable.
- **Typologies territoriales et régions linguistiques** : leur état communal n'a pas été testé. Même procédure à
  appliquer (étape 1), surtout pour les versions anciennes (typologie 2012).
- **Suisses de l'étranger** : dans BE, TI, GR, JU, NE, SO, …, ils sont inscrits dans leur commune. `eligible_voters`
  n'y est donc pas comparable à la population résidente. Cela affecte une éventuelle feature « participation » ou
  « taille de l'électorat », pas la géographie.
- **Clavaleyres → Murten (BE → FR, 2022)** : effet trop petit pour être mesuré ; on suppose qu'il est traité comme
  une fusion ordinaire.
- **Pics ponctuels d'électeurs inscrits** (environ 90 communes) : à signaler à l'OFS ou à filtrer dans les features
  de participation.

# Audit des données municipales V2

**État vérifié le 23 novembre 2026.** Cet audit décrit la population assemblée,
ses sources et leurs limites de disponibilité. Il ne présente aucun modèle,
score ou résultat individuel de votation. Le statut demeure
**`strict_forecast_ready=false`** : les archives des versions effectivement
disponibles avant chaque scrutin ne sont pas établies pour l'ensemble des
sources.

## 1. Population retenue et exclusions

Le [manifeste V2 round2](../../reports/generated/municipal_v2_round4/data_manifest.json)
et sa [couverture annuelle](../../reports/generated/municipal_v2_round2/coverage_by_year.csv)
décrivent une table à clé unique `municipality_id × vote_id` :

| Périmètre | Valeur vérifiée |
| --- | ---: |
| Lignes commune × objet | 797 596 |
| Objets fédéraux distincts | 380 |
| Dates de votation distinctes | 133 |
| Communes distinctes | 2 105 |
| Premier scrutin retenu | 5 avril 1981 |
| Dernier scrutin retenu | 28 septembre 2025 |
| Lignes perdues dans les jointures | 0 |

La cible prévue est la proportion communale de oui parmi les oui et non.
Le [constructeur de table](../../scripts/integration/build_modeling_dataset.py)
vérifie les identifiants et dates, conserve les observations avec covariables
manquantes et interdit qu'une jointure multiplie ou supprime des lignes.

Les **1 025 903** lignes du parquet OFS sont filtrées dans cet ordre :

| Exclusion successive | Lignes retirées |
| --- | ---: |
| Unités spéciales | 3 190 |
| Questions subsidiaires initiative/contre-projet | 8 414 |
| Observations marquées provisoires | 18 945 |
| Bulletins valables supérieurs aux bulletins rentrés | 4 |
| Somme oui/non supérieure aux bulletins valables | 81 |
| Cible indéfinie après les filtres précédents | 0 |

Il reste 995 269 observations utilisables pour l'historique ; 197 673 sont
antérieures à 1981 et ne deviennent pas des lignes de la table V2. Elles peuvent
contribuer au contexte historique communal. La note OFS signale que la période
1960–1980 est incomplète, notamment pour FR, AG et TI : cet historique ancien
n'est donc pas une couverture nationale homogène.

**Le départ en 1981 suit cette rupture de couverture documentée.** Commencer
en 1960 ajouterait des années sans ces trois cantons et modifierait la
population représentée ; l'allongement apparent de l'historique ne suffirait
pas à justifier cette différence de couverture. Ce choix ne remplace pas les
contrôles d'intégrité des observations à partir de 1981.

### Pourquoi novembre 2025 est absent

Les objets `6800` (« Initiative service citoyen ») et `6810` (« Initiative pour
l'avenir »), du 30 novembre 2025, existent dans OFS et Swissvotes. Chacun compte
2 105 lignes communales ordinaires, toutes marquées `is_provisional=True`, et
12 unités spéciales. Les 4 210 lignes communales sont exclues avant les
jointures.

La [capture officielle du 23 novembre 2026](../../data/external/ofs_metadata_20261123/README.md)
confirme que la note du cube actuel classe encore **novembre 2025, mars 2026 et
juin 2026** comme provisoires. `LAST-UPDATED` indique le 21 août 2026 à 08:30.
Le statut local reste conforme à cette note ; les valeurs du cube complet
n'ont pas été comparées. Les résultats provisoires ne sont pas requalifiés
manuellement pour étendre la période disponible.

## 2. Géographie, démographie et élections locales

Le jeu suit le mode `retrospective_fixed_2026_geography` : les résultats sont
harmonisés sur les communes au **1er janvier 2026**. Les typologies communales
sont également statiques. Les limites communales, les classifications et les
éditions de données n'ont donc pas toutes leur version historique propre à
chaque date de votation. La source OFS décrit notamment le transfert de Moutier
de Berne au Jura dans cette géographie.

| Période dans la table | Lignes | Objets | Dates | Couverture locale constatée |
| --- | ---: | ---: | ---: | --- |
| 1981–2011 | 534 615 | 255 | 89 | Démographie STATPOP et parts électorales locales absentes dans cet assemblage |
| 2012–28 septembre 2025 | 262 981 | 125 | 44 | Population renseignée ; quelques observations électorales restent entièrement manquantes |

Cette absence avant 2012 décrit **les sources actuellement intégrées**, sans
affirmer que des sources historiques plus anciennes n'existent pas. Les
valeurs récentes ne sont jamais reportées artificiellement vers les dates
anciennes. Une part électorale manquante pour un parti reste distincte d'une
part nulle ; le PDC, le PBD et Le Centre ne sont pas fusionnés rétroactivement.

Les jointures choisissent la dernière observation admissible avant la veille
du scrutin. Pour STATPOP, le seuil de sélection est le 2 septembre de l'année
suivante ; pour les élections, le 1er janvier de l'année suivante. Ces règles
sont des hypothèses conservatrices de sélection, **pas des preuves de
publication pour chaque observation**. Les typologies et Swissvotes couvrent
toutes les lignes ; le premier domaine politique est renseigné, mais les
domaines secondaires ne le sont pas toujours. L'historique communal initial
reste manquant sur 55 lignes.

## 3. Sens politique et sens supposé d'un oui

Le [bloc politique](../../scripts/modeling/political_features_v2.py) utilise
les recommandations de partis et d'institutions, les votes parlementaires
finaux et des domaines détaillés de Swissvotes. Une recommandation explicite
oui/non devient respectivement `+1`/`−1`. L'absence de recommandation, la liberté
de vote, un parti inexistant et une valeur manquante restent des catégories
distinctes ; elles ne deviennent pas une opposition implicite.

Les interactions locales combinent ces recommandations avec les parts
électorales antérieures observées. Les agrégats nationaux `ja-lager` et
`nein-lager` décrivent le poids électoral des camps selon Swissvotes, sans lire
le résultat populaire de l'objet. Ces indications décrivent des soutiens
politiques ; elles ne suffisent pas à définir l'effet juridique d'un oui.

Le [bloc lexical](../../scripts/modeling/direction_features_v2.py), version
`title_direction_v2.1`, recherche dans les titres officiels et courts des
indices explicites de direction sur huit axes : environnement, fiscalité,
soutien social public, immigration, coopération internationale, engagement
militaire, égalité civile et restrictions réglementaires. Il s'agit de
**proxies lexicaux expérimentaux**, sans validation humaine de l'effet de chaque
objet. Une absence de correspondance ou une ambiguïté reste inconnue, jamais
automatiquement neutre. La couverture est faible : entre 3 et 12 objets
renseignés par axe sur 380, avec chevauchements possibles.

Les titres courts sont des métadonnées éditoriales. Les dates de publication
historiques des titres et recommandations de l'édition Swissvotes courante
ne sont pas attestées objet par objet. Les textes de brochures dont les
correspondances restent non validées sont exclus de ces variables.

## 4. Sondages SSR / gfs.bern

La [collecte documentée](../../data/external/polls/README.md) contient
**96 lignes pour 48 objets**, avec deux vagues par objet : 44 objets de
2021–2025 et quatre objets du 29 novembre 2026. Seuls **42 des 44 objets
historiques** appartiennent à la table V2 ; les deux absents sont ceux de
novembre 2025, exclus pour leur statut provisoire. Les sondages futurs de
novembre 2026 ne créent aucune ligne d'entraînement.

L'enrichissement retient un sondage admissible pour 42 objets, soit 88 410
lignes communales. Les 338 autres objets restent présents, avec une absence
explicite de sondage. La collecte n'a pas récupéré d'archive structurée avant
2021 ; aucune valeur n'est inventée pour combler cette période. Les
correspondances reposent sur la date, l'identifiant et des titres revus.

La vague sélectionnée doit avoir été publiée avant l'instant de prévision.
Le cutoff préparé est la veille du scrutin à minuit ; il permet donc une
information de fin de campagne, sans démontrer qu'elle était disponible à un
horizon plus ancien. Les dates annoncées sont conservées, mais les versions
historiques des pages et graphiques ne sont pas certifiées. Certaines
métadonnées de modification sont postérieures au vote : cela ne démontre pas
une modification des chiffres, mais empêche d'affirmer leur identité avec la
publication initiale.

Les sondages concernent l'intention nationale déclarée. Le poids démographique
éventuellement associé, `population × (1 − part étrangère) × (1 − part 0–19 ans)`,
est une approximation de la population électorale résidente : elle ignore les
dépendances âge/nationalité, omet les électeurs de 18–19 ans, les expatriés et
la participation. Aucun décompte du scrutin évalué ne sert à ce poids.

## 5. Traçabilité et limites restantes

Le manifeste conserve les empreintes des cinq parquets sources, du fichier de
sondages et du dataset assemblé. Références de cette vérification :

- Dataset V2 :
  `cdbe2331bf50d5aef94fd0b7c89ccaf36d0a8321ba00807fe2aad42bd691a85c`.
- Manifeste `municipal_v2_round4/data_manifest.json` :
  `b5675ef7fb6e4e81c0bbee994484eb8d59190ae5348e53863942f2e76faa3347`.
- [Capture OFS et provenance](../../data/external/ofs_metadata_20261123/metadata.json),
  [provenance des sondages](../../data/external/polls/provenance.json) et
  [preuves des sources de sondages](../../data/external/polls/source_evidence.json).

Les priorités de données sont d'obtenir des versions historiques datées,
d'intégrer des covariables locales plus anciennes avec leur provenance, de
valider humainement l'effet d'un oui et les correspondances des brochures,
puis d'actualiser les résultats définitifs à partir du statut publié par OFS.
Les horodatages supposés et la géographie harmonisée maintiennent le statut
exploratoire rétrospectif. Le simple contrôle d'une date antérieure au scrutin
ne suffit pas à certifier un jeu de prévision historique strict.

### Sources primaires

- [OFS — cube communal et notes](https://www.pxweb.bfs.admin.ch/pxweb/fr/px-x-1703030000_101/px-x-1703030000_101/px-x-1703030000_101.px/).
- [Swissvotes — dataset](https://swissvotes.ch/page/dataset) et
  [codebook](https://swissvotes.ch/page/dataset/codebook-de.pdf), notamment les
  définitions des recommandations, des positions institutionnelles et des
  camps électoraux.
- [gfs.bern — sitemap des publications](https://cockpit.gfsbern.ch/de/wp-sitemap-posts-cpt_cockpit-1.xml) ;
  les URL des pages et tableaux effectivement utilisés figurent dans la
  provenance conservée avec la collecte.

Le [manifeste final versionné](../../reports/datasets/municipal_v2_20261123/data_manifest.json) ajoute les variables de tendance entre vagues sans modifier la population ni les cibles. Les manifestes des quatre séries (dont une répétition de portabilité) sont conservés avec le rapport.

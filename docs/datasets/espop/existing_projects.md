# Raccordements existants : RTS, Zurich et SMMT

**Recherche et contrôles :** 27 octobre 2026.
**Suite de :** [audit ESPOP #65](https://github.com/VictorGTheCoder/GML-Swiss-Voting/issues/65).
**Tâche de validation :** [#67 — réutilisation des données et correspondances](https://github.com/VictorGTheCoder/GML-Swiss-Voting/issues/67).

## Conclusion exploitable

Des fichiers et outils existants peuvent réduire le travail de préparation.
La meilleure piste de données est la RTS : ses séries historiques et ses classes
d'âge utilisent déjà les 2 110 codes de notre référence communale du 01.01.2026.
Le fichier annuel population/nationalité conserve toutefois trois anciennes
communes ESPOP non résolues. SMMT fournit une méthode de correspondance
historique documentée, avec des cas explicitement non raccordables.

**Recommandation à valider par une tâche distincte :** comparer les fichiers RTS
aux sources OFS, puis vérifier les correspondances SMMT sur un échantillon de
mutations. Réutiliser ce qui est démontré compatible, plutôt que reconstruire
toute l'harmonisation. Cette recherche ne valide ni leur intégration au modèle,
ni leur admissibilité à l'instant de prédiction.

La période principale provisoire reste 2012–2025. Aucune source contrôlée ici
ne fournit simultanément les trois parts d'âge communales annuelles avant 2010
et la résolution démontrée des exceptions ESPOP.

## 1. RTS : fichiers effectivement téléchargés

La [publication RTS reprise sur Swissinfo](https://www.swissinfo.ch/fre/le-meilleur-du-contenu-ssr/comment-la-population-a-chang%C3%A9-en-suisse-depuis-votre-naissance/91258528)
annonce l'usage de STATPOP, ESPOP et des recensements, avec harmonisation des
communes vers 2026. Son [application publique](https://rtsinfo-data.s3.eu-central-1.amazonaws.com/vt/2026/demographie-naissance/build/index.html)
charge les CSV du dossier `clean_data/`. Les liens ci-dessous sont les fichiers
réellement inspectés, et non des URL supposées.

| Fichier | Contenu et couverture contrôlés | Usage envisageable |
| --- | --- | --- |
| [Population historique](https://rtsinfo-data.s3.eu-central-1.amazonaws.com/vt/2026/demographie-naissance/build/clean_data/data_communes_historique.csv) | 29 852 lignes ; `Code`, `Année`, `Population` ; 14 dates de 1900 à 2020 | Référence de comparaison du raccordement des recensements. |
| [Nationalité historique](https://rtsinfo-data.s3.eu-central-1.amazonaws.com/vt/2026/demographie-naissance/build/clean_data/proportion_population_etrangere_historique.csv) | 29 852 lignes ; population étrangère et totale ; mêmes 14 dates | Calcul d'une part étrangère aux dates de mesure. |
| [Population et nationalité annuelles](https://rtsinfo-data.s3.eu-central-1.amazonaws.com/vt/2026/demographie-naissance/build/clean_data/proportion_population_etrangere_etat_actuel.csv) | 94 072 lignes ; `Année`, `Code`, `Population_etrangere`, `Population_totale` ; 1981–2024 | Source candidate du bloc population/nationalité historique. |
| [Classes d'âge historiques](https://rtsinfo-data.s3.eu-central-1.amazonaws.com/vt/2026/demographie-naissance/build/clean_data/population_classes_age_historique.csv) | 64 005 lignes ; `Année`, `Code`, `Classe_age`, `Population` ; 10 dates de 1941 à 2020 | Variante ponctuelle avec âge des recensements. |
| [Classes d'âge récentes](https://rtsinfo-data.s3.eu-central-1.amazonaws.com/vt/2026/demographie-naissance/build/clean_data/population_classes_age_etat_actuel.csv) | 96 075 lignes ; mêmes champs ; 2010–2024, annuel | Comparaison aux agrégations STATPOP du projet. |

Les fichiers comprennent aussi des agrégats non communaux : ne pas interpréter
le nombre total de lignes comme une couverture communale. Contrôle réalisé :
lecture pandas avec `dtype={'Code': str}`, sélection des codes entièrement
numériques, comparaison au snapshot local
`data/raw/geography/register_snapshot_2026-01-01.csv`, niveau communal `Level=3`.

- Pour les quatre fichiers historiques ou d'âge, les codes communaux distincts
  correspondent exactement aux 2 110 codes du snapshot, sans code supplémentaire
  ni manquant. Aucune clé commune/année, ou commune/année/classe d'âge, dupliquée.
- Le fichier annuel population/nationalité contient 92 972 lignes à code numérique,
  sur 2 113 codes : les 2 110 actuels et **4505, 4670, 4695**. Il n'a aucun doublon
  code/année, aucune valeur manquante ou négative dans les deux effectifs, mais
  **266 totaux nuls**. Ces cas demandent une analyse avant toute division.
- Les dates de population historique sont 1900, 1910, 1920, 1930, 1941, 1950,
  1960, 1970, 1980, 1990, 2000, 2010, 2015, 2020.
- Les dates d'âge historique sont 1941, 1950, 1960, 1970, 1980, 1990, 2000,
  2010, 2015, 2020. Les classes sont **0–19, 20–64, 65+** : elles ne permettent
  pas de retrouver `share_age_20_39` sans source supplémentaire.

Ces vérifications portent sur le schéma, les clés, les périodes et certains
contrôles arithmétiques ; elles ne certifient pas les valeurs ni la méthode de
répartition lors de chaque mutation. Une égalité de codes n'établit pas à elle
seule l'égalité des territoires ou des dénominateurs.

Les CSV sont accessibles publiquement, mais leur licence de redistribution
spécifique et le code de préparation complet n'ont pas été établis. Avant de
versionner une copie dans le projet, documenter les conditions de réutilisation.
La publication de l'application en 2026 ne prouve pas la disponibilité historique
des valeurs avant chaque brochure. Les interpolations et projections de
l'application ne sont pas proposées comme observations pour notre modèle.

## 2. Canton de Zurich : population ESPOP/STATPOP déjà préparée

Le dépôt [awelZH/energy](https://github.com/awelZH/energy) publie le
[script de préparation](https://github.com/awelZH/energy/blob/main/analyse/04_data_bev_gem.R)
et [la table `bev_gem.csv`](https://github.com/awelZH/energy/blob/main/data/input/bev_gem.csv).
Version du fichier repérée : commit
[`cbee3824065e206120aa06d4f9a0b083ef676e8e`](https://github.com/awelZH/energy/blob/cbee3824065e206120aa06d4f9a0b083ef676e8e/data/input/bev_gem.csv).

Contrôle du CSV téléchargé : 91 977 lignes, 2 139 codes, années 1981–2023,
colonnes `bfs`, `gem`, `ktid`, `kt`, `jahr`, `value`, `komponente` ; aucune clé
`bfs/jahr` dupliquée. La mesure est l'effectif au 31 décembre, nationalité et
sexe Total. Le script utilise le même cube OFS `_201` que notre audit et ajoute
le canton à partir du répertoire communal.

Le script garde explicitement les trois codes exceptionnels et leur attribue
la Thurgovie. Il ne résout pas leur répartition territoriale. Ce fichier peut
servir de comparaison et éviter un export manuel, mais il ne contient pas
l'âge ni la ventilation de nationalité nécessaire à `share_foreign`.
Le dépôt déclare une licence GPL-3.0 ; conserver séparément les conditions de la
source OFS et celles du code, sans inférer une licence propre à chaque donnée.

## 3. SMMT : réutiliser les correspondances historiques

[SMMT sur GitHub](https://github.com/ValValetl/SMMT) est un outil R universitaire
documenté dans un [article de Knechtl et Stutzer](https://pmc.ncbi.nlm.nih.gov/articles/PMC9344967/).
L'article illustre une fusion de résultats de votations de 1983 et 2017 :
correspondance des communes, somme des oui/non, puis recalcul des parts.

Le [manuel](https://smmt.valentinknechtl.ch/articles/manual.html) montre
`map_old_to_new_state` et ses sorties `mapped` et `unmapped`. Les cas non
raccordables, notamment certaines scissions, restent signalés. Le code est
disponible sous GPL-3. SMMT produit des correspondances ; il ne fournit pas
un dataset démographique ESPOP/STATPOP complet et ne fabrique pas les poids
manquants. Aucun raccordement SMMT sur nos données n'a encore été exécuté.

Une [autre bibliothèque, swissMunicipalities](https://github.com/SwissStatsR/swissMunicipalities),
expose les snapshots, mutations et correspondances de l'API OFS, notamment
`get_correspondances`. C'est une alternative pour obtenir une table officielle
de correspondance ; ce n'est pas non plus une table démographique fusionnée.

## 4. Autres pistes examinées

- [Troxler, Roller et Bandi Tanner, 2024, section 3.5](https://link.springer.com/article/10.1186/s41937-024-00127-0)
  : raccordement documenté des recensements, ESPOP et STATPOP ; l'article ne
  fournit pas un téléchargement public de la table démographique complète.
  Piste méthodologique, sans accès direct établi aux données préparées.
- [MikeSpa/swiss-maps](https://github.com/MikeSpa/swiss-maps/blob/main/pipeline/DATA_SOURCES.md)
  : joint plusieurs sources communales, mais la documentation indique STATPOP
  2010–2024 comme non encore intégré dans un script autonome. Pas de solution
  vérifiée à l'extension ESPOP ou à l'âge annuel historique.

## Travail restant et critères de réutilisation

La tâche associée doit livrer une décision de réutilisation par bloc, étayée par
un prototype limité : comparer RTS à OFS sur des années charnières, inspecter
les dénominateurs nuls et les trois exceptions, essayer les correspondances
historiques, puis rapporter pertes de couverture, différences et conditions
de publication/licence. Si une piste échoue, conserver le constat et la solution
de repli OFS ; ne pas imposer l'adoption d'un outil.

La production d'un pipeline historique complet, l'ajout des mouvements
démographiques à la V1 et le changement de période restent hors de cette tâche.

## Identification des fichiers RTS contrôlés

Empreintes SHA-256 calculées sur les octets téléchargés le 27 octobre 2026.
Les URL publiques sont susceptibles d'être mises à jour ; les fichiers contrôlés
restent localement sous `.scratch/espop65/rts_*.csv`, hors Git.

| Fichier dans `clean_data/` | SHA-256 |
| --- | --- |
| `data_communes_historique.csv` | `c333f0b4fe22188759056d901351e1c286aaa408d4b291e0e08ec76cfa01892a` |
| `proportion_population_etrangere_historique.csv` | `ef157769035bdad297707dfe69558a351b61c3e638b09ad1708aaae0a92a674e` |
| `proportion_population_etrangere_etat_actuel.csv` | `4045c3ba7507abab9bba8c74a1ef75f70a1c4505735f5acaa4f5fb078dedabe7` |
| `population_classes_age_historique.csv` | `851e1e69d5acfb4a31cb8e9b8f2899792ace08cb304b82afcdc829fac3095eee` |
| `population_classes_age_etat_actuel.csv` | `d431780daf5a963f6f43fe3769d3d986ad116c8c993692967e722f54f8a854ab` |

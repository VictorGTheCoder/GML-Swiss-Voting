# Enrichissement des votations et profils communaux — 23 novembre 2026

## Résultat principal

La collecte de sondages historiques ajoute **48 observations pour 24 objets et
10 dates complètes de 2016 à 2020**. Avec les paramètres de tendance déjà fixés
dans V2, elle ramène la MAE de développement de **8,1181 à 7,6183 points**.
L'objectif de quatre points n'est pas atteint. Un encodage des thèmes comme
ensembles améliore séparément le modèle structurel de **9,4210 à 9,0457 points**.

Tous les scores ci-dessous portent sur les mêmes **66 objets, 23 dates et
138 868 observations communales de 2016–2022**. Il s'agit du développement déjà
exploré. La période 2023–2025 n'a pas été réévaluée, le candidat V2 n'a pas été
remplacé et sa capture prospective du 29 novembre 2026 reste intacte.

Le [registre des résultats](results.json), la [campagne structurelle](structural_campaign.json),
la [comparaison des sondages](polling_comparison.json) et le
[plan déclaré avant les nouveaux scores](../../../experiments/municipal_v3/plan.json)
conservent paramètres, hypothèses, métriques, environnements et empreintes.

## 1. Ce qui a réellement été ajouté aux données

### Sondages antérieurs à 2021

La [nouvelle collecte](../../../data/external/polls_historical_v3/README.md)
contient deux vagues nationales par objet. Les dates et identifiants ont été
appariés sans consulter les résultats populaires ni les erreurs des modèles.
Tous les objets de chaque date choisie sont inclus. Le choix des dates dépend
de sources primaires récupérables ; il ne constitue pas une couverture exhaustive.

La couverture du développement passe de **24/66 à 48/66 objets**, soit 36,4 %
à 72,7 %. Les 18 objets encore sans sondage restent dans le score et utilisent
le même repli structurel. Les nouvelles sources viennent de SRF, SWI et de
rapports gfs.bern conservés par Année Politique Suisse. Exemple vérifiable :
les publications originales de la sortie du nucléaire en 2016 donnent
[57/36/7](https://www.srf.ch/news/schweiz/atomausstiegs-initiative-57-prozent-fuer-atomausstiegs-initiative)
puis [48/46/6](https://www.srf.ch/news/schweiz/srg-umfrage-atomausstiegs-initiative-ja-und-nein-halten-sich-die-waage)
pour oui/non/indécis.

Les 48 triplets sont explicitement publiés ; aucun indécis n'est reconstitué
par différence. Les sources et décisions de résolution des incohérences sont
dans [evidence.json](../../../data/external/polls_historical_v3/evidence.json).
38 des 40 sources ont une empreinte binaire. Les deux rapports PDF de mars 2018
ont été inspectés via l'outil PDF, mais leur téléchargement direct a retourné
403 ; leurs quatre observations ne revendiquent pas de hash binaire.

Ce sont des intentions nationales parmi les personnes qui prévoient de voter,
pas des sondages municipaux. L'ancrage V2 conserve sa pondération démographique
approximative et son contrôle de couverture ; la moyenne simple des communes
n'est pas assimilée au résultat national.

### Informations d'objet inutilisées jusque-là

Le [nouveau tableau d'objets](../../../data/processed/municipal_v3/README.md)
contient **380 lignes et 32 variables supplémentaires** : 24 catégories de
recommandations d'organisations économiques, agricoles, syndicales,
professionnelles ou territoriales, et huit descriptions de procédure.
Les mots d'ordre gardent leurs états distincts ; les signatures exigent des
dates de dépôt et de certification antérieures au scrutin. Les définitions
proviennent du [codebook Swissvotes](https://swissvotes.ch/page/dataset/codebook-de.pdf).

Ces colonnes enrichissent l'usage du snapshot Swissvotes déjà présent ; elles
ne représentent pas de nouveaux résultats de votation. Les champs post-vote,
résumés rétrospectifs et totaux finaux de campagne ne sont pas utilisés.
Les données locales de revenu, logement et activité restent des acquisitions
suivantes, identifiées plus bas mais non injectées dans cette campagne.

### Thèmes multiples

V2 dispose déjà de domaines et sous-domaines. Le nouvel essai traite les thèmes
comme un ensemble : le même domaine active la même colonne qu'il apparaisse
en première, deuxième ou troisième position dans Swissvotes. La hiérarchie
est conservée, et le vocabulaire est appris sur le train de chaque fenêtre.
Il s'agit d'un changement de représentation, pas d'une annotation nouvelle du
sens juridique d'un oui.

## 2. Résultats des six hypothèses structurelles

Les têtes XGBoost, le début d'entraînement en 1990 et les fenêtres sont repris
du candidat V2. Les six hypothèses sont déclarées ensemble, sans recherche de
paramètres après lecture de leurs scores. Les sondages actuels désignent
exactement la collecte V2, sans les nouvelles observations historiques.

| Variante | MAE structurelle | Avec sondages actuels et tendance |
| --- | ---: | ---: |
| Référence PCA5 | 9,4210 | 8,1181 |
| + recommandations d'organisations | 9,3797 | 8,2198 |
| + procédure et signatures | 9,5851 | 8,3726 |
| Thèmes encodés comme ensembles | **9,0457** | **8,0404** |
| Organisations + procédure + thèmes en ensembles | 9,2968 | 8,4343 |
| Six prototypes communaux souples, cinq dimensions | 9,6259 | 8,3543 |

Le gain des organisations seules est trop petit pour motiver leur adoption.
La procédure n'améliore pas cette configuration. Tout ajouter ne donne pas
le meilleur résultat. Les thèmes en ensembles améliorent les trois fenêtres :
9,3323 → 9,0768 en 2016–2018, 7,3819 → 7,2305 en 2019–2020, et 10,5515 → 9,9144
en 2021–2022.

Le bootstrap apparié de dates donne pour cette dernière différence une plage
descriptive à 95 % de **−0,716 à −0,068 point**. Elle décrit les dates de
développement réutilisées ; elle ne corrige ni la sélection passée ni les
comparaisons multiples et ne certifie pas un gain futur.

### Extension des sondages, modèle structurel inchangé

La comparaison suivante réutilise les mêmes prédictions structurelles déjà
enregistrées. Aucun réentraînement ni réglage de tendance ne confond l'effet
de la collecte supplémentaire.

| Couverture et traitement | Objets avec sondage | MAE |
| --- | ---: | ---: |
| Collecte V2, dernière vague seule | 24/66 | 8,4548 |
| Collecte V2, tendance fixée V2 | 24/66 | 8,1181 |
| Collecte élargie, dernière vague seule | 48/66 | 8,5707 |
| Collecte élargie, tendance fixée V2 | 48/66 | **7,6183** |

Le gain de 0,4998 point dépend de l'exploitation de la dynamique entre vagues.
La seule dernière vague peut conserver un biais de campagne et n'améliore pas
cette population. Le bootstrap apparié par date de la différence
« élargie avec tendance − V2 avec tendance » donne **[−1,298 ; +0,080] point**.
Cette incertitude et la réutilisation du développement empêchent de présenter
le gain de 0,50 point comme garanti.

### Sensibilité aux dates centrales des enquêtes

21 des nouvelles lignes ont un jour de référence annoncé ; 27 utilisent le
milieu arithmétique de la période de terrain, clairement marqué comme approximé.
Une vérification séparée déplace seulement ces milieux vers leurs bornes,
selon quatre scénarios fixés avant calcul. Les parts, publications et paramètres
du modèle restent inchangés.

Le nominal est reproduit exactement. Les quatre scores sont **7,6262 ; 7,6855 ;
7,6476 ; 7,6117**, contre 7,6183 au nominal. Le gain global résiste donc à cette
vérification. Certaines prévisions individuelles changent jusqu'à **6,28 points** :
la stabilité de la moyenne ne signifie pas que chaque commune est stable.
Cette plage de quatre scénarios n'est ni un intervalle de confiance ni une
borne exhaustive de toutes les variations possibles objet par objet. Voir les
fichiers `poll_timing_*` de ce dossier.

## 3. Corrélations et redondances : deux audits nécessaires

L'[audit avant encodage](correlation_audit.json) distingue les objets, les
snapshots communaux, les historiques et les interactions. Il ne charge pas
la cible. Une variable d'objet est comptée une fois par votation, pas deux mille
fois parce qu'elle est répétée pour les communes.

Sur les trois trains, aucune paire brute contrôlée ne satisfait à la fois la
relation affine parfaite, une couverture manquante identique et un support
d'au moins 20 unités. Exemple : les directions Conseil fédéral et Parlement
ont Pearson = 1 sur leurs 277 valeurs communes avant 2021, mais leurs masques
de valeurs manquantes diffèrent.

L'[audit après le prétraitement V2 exact](correlation_encoded_audit.json) révèle
en revanche des redondances introduites ou rendues visibles par l'imputation
et le one-hot :

| Train avant | Objets | Variables brutes | Colonnes encodées | Constantes | Paires exactes | Autres paires affines |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2016 | 240 | 42 | 340 | 3 | 69 | 32 |
| 2019 | 270 | 42 | 353 | 3 | 64 | 32 |
| 2021 | 282 | 42 | 357 | 3 | 60 | 32 |

Avant 2021, les **92 paires** impliquent 115 colonnes différentes ; elles ne
signifient pas 92 variables supprimables. 85 paires apparaissent dans les trois
trains. 68/92 impliquent au moins une valeur présente moins de cinq fois.
Le rang numérique est 200 pour 357 colonnes, sans que ce rang constitue un
critère automatique de sélection pour les arbres.

Certaines relations sont lisibles : direction PLR et dummy « PLR non », ou
directions Parlement et Conseil national après imputation. D'autres sont des
coïncidences entre catégories rares. Deux dummies complémentaires sur le train
peuvent devenir toutes deux nulles pour une catégorie inconnue. La suppression
doit donc préserver les états inconnus et être ajustée puis évaluée à l'intérieur
de chaque fenêtre. Aucun gain de suppression de colonnes n'est revendiqué ici.

L'audit donne Pearson et Spearman. Une faible corrélation linéaire avec la cible
ne suffit pas à retirer une variable d'un modèle avec interactions. Pour les
variables corrélées, les ablations de groupes complètent mieux l'analyse que
les importances par permutation isolées ; voir la
[documentation scikit-learn](https://scikit-learn.org/stable/auto_examples/inspection/plot_permutation_importance_multicollinear.html).

## 4. Ce que montre le test de prototypes

Six centres KMeans sont appris sur les seuls profils historiques des communes,
centrés par objet. Des poids de proximité continus, centrés puis orthonormalisés,
produisent cinq dimensions ; les têtes XGBoost sont celles de la référence.
Les objets d'évaluation ne participent ni aux centres, ni aux profils, ni aux
transformations. Une commune inconnue reçoit la moyenne d'objet prévue.

Cette représentation obtient **9,6259**, contre **9,4210** pour PCA5. Elle n'est
donc pas retenue. Les poids décrivent la proximité de communes, pas une proportion
de personnes appartenant à un « type d'électeur ». Des observations agrégées
ne permettent pas cette interprétation individuelle.

[e-means](https://e-means.github.io/) optimise le même objectif de regroupement
que k-means avec une autre procédure. Ses auteurs rapportent des gains de
vitesse et d'inertie ; cela n'établit pas un gain de prédiction des votes.
Cette campagne a testé KMeans comme référence pour l'idée des prototypes.
Elle n'a pas exécuté e-means, et ne conclut pas qu'aucune autre base de profils
ne pourrait améliorer le modèle.

Le diagnostic structurel V2 donne **5,6185 points** après soustraction oracle
du biais médian propre à chaque objet. Ce calcul utilise les résultats observés :
ce n'est pas une prévision. Il indique que même une correction idéale de ce
seul décalage laisserait un problème dans les contrastes locaux du modèle actuel.

## 5. Prochaine acquisition à plus forte valeur attendue

### Effet concret d'un oui, avec preuve textuelle

La piste principale est une représentation de la mesure : instrument employé,
sens du changement, financement, groupes directement concernés et application.
Un objet peut agir simultanément sur plusieurs dimensions. « Environnement »
ne dit pas s'il crée une taxe, une interdiction, une subvention ou une obligation.
L'absence d'information doit rester distincte d'un effet nul ou mixte.

Le [contrat d'annotation proposé](../../../experiments/municipal_v3/semantic_annotation_contract.json)
prévoit une correspondance d'objet validée, la source officielle, ses pages,
une preuve d'effet et un statut de revue. Il n'est pas un nouveau jeu de labels
déjà validés. Les textes explicatifs rédigés après le vote et mentionnant son
résultat doivent rester hors de la génération des prédicteurs.

### Exposition locale à cette mesure

La valeur attendue vient du croisement entre le contenu de l'objet et les
caractéristiques pertinentes de la commune. Ces variables sont des hypothèses
à tester, pas des explications causales établies :

| Acquisition | Variables candidates | Source et contrôle à réaliser |
| --- | --- | --- |
| Revenu et fiscalité | distributions de revenus, structure des contribuables, charge fiscale | [AFC, communes depuis 1983](https://www.estv.admin.ch/fr/statistiques-personnes-physiques-communes-1983-a-aujourdhui) ; respecter la publication et les changements de communes |
| Activité économique | poids de l'agriculture, de l'industrie et des services, emplois | [OFS STATENT, 2011–2024](https://statistik.admin.ch/fr/asset/36734273) ; calendrier, géographie et cellules non diffusées |
| Logement | propriété/location lorsque disponible, parc, vacance, résidences secondaires | [OFS parc de logements](https://statistik.admin.ch/fr/asset/36827979), [ARE inventaire](https://www.are.admin.ch/fr/inventaire-logements) ; couverture et définitions communales |
| Écarts régionaux de campagne | ventilations linguistiques ou partisanes des sondages | Sources SSR/gfs originales ; effectifs, incertitudes et cohérence avec l'ancre nationale |
| Divergences partisanes cantonales | consignes cantonales explicitement documentées | Swissvotes `pdev-*` ; un blanc peut signifier accord ou information absente |

Un millésime n'est pas une date de disponibilité. Par exemple, l'AFC a publié
les chiffres fiscaux 2023 en novembre 2026 ; les emplois STATENT 2024 ont été
publiés en août 2026. Ces valeurs ne peuvent pas être injectées comme des
observations connues en 2023 ou 2024. Les séries rétrospectives actuelles
nécessitent également un contrôle des versions.

Les [enquêtes VOX/VOTO](https://www.voto.swiss/les-enquetes-voto/?lang=fr)
documentent les motivations après scrutin. Elles peuvent éclairer des dimensions
apprises sur des objets antérieurs, avec pondérations et regroupements appropriés.
Leurs réponses au scrutin évalué ne constituent pas une information pré-vote,
et leur taille ne fournit pas un sondage représentatif de chaque commune.

## 6. Reproduction et statut du travail

Le [guide V3](../../../docs/project/municipal_v3.md) donne les commandes.
Une première exécution a été interrompue avec le code 137 lors de l'encodage
des domaines, compatible avec un manque de mémoire. Le
[registre interrompu](interrupted_campaign.json) conserve trois variantes
complètes, sans score global attribué aux variantes inachevées. La reprise
charge seulement les colonnes nécessaires et stocke les indicateurs de thèmes
en entiers sur un octet. Les trois prédictions déjà achevées sont reproduites
bit à bit ; les six hypothèses et paramètres sont inchangés.

Les nouveaux tests portent sur les codes invalides, clés et dates, vocabulaire
ajusté au train, catégories inconnues, cibles absentes à la prédiction, prototypes,
ancrage, empreintes et sensibilité des dates. Une revue indépendante a conduit
au renforcement des contrôles de provenance avant la campagne finale.

Le statut reste **expérimental et rétrospectif**, avec `strict_forecast_ready=false`.
Les quatre points sont un objectif de MAE moyenne par objet, pas une erreur
maximale garantie pour chaque commune. Les données et les essais sont livrés
comme une suite vérifiable de la recherche, avec leurs résultats défavorables
et leurs incertitudes.

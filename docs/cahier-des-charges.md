# Cahier des charges - Tendances et prédiction des votations fédérales suisses

**Cours :** Gestion et valorisation de projet ML, HEIG-VD

**Équipe A01 :** Kimberly Beyeler, Romain Durussel, Victor Giordani, Abram Zweifel  

**Version de travail :** 22 septembre 2026

## 1. Contexte et problématique

La Suisse vote régulièrement sur des objets fédéraux touchant à des domaines variés, comme la fiscalité, l’environnement ou les institutions. L’Office fédéral de la statistique publie les résultats jusqu’au niveau communal. Cette précision permet de constater que le soutien à un même objet varie d’une commune à l’autre, parfois au sein d’un seul canton. Mais chaque carte de résultats ne montre qu’un scrutin : elle ne dit pas si les différences observées se répètent, ni si elles changent selon le sujet soumis au vote.

En réunissant plusieurs années de votations, on peut confronter les résultats antérieurs des communes aux caractéristiques de leur territoire et aux thèmes des objets. La première question est alors de savoir si ces informations sont réellement utiles pour anticiper un scrutin qui n’a pas servi à construire le modèle : **dans quelle mesure permettent-elles d’estimer la part de « oui » par commune pour un nouvel objet fédéral ?** La réponse sera mesurée sur des votations historiques réservées à l’évaluation, en comparant le modèle à des estimations simples.

La performance moyenne d’un modèle ne résume cependant pas toutes les dynamiques locales. Certaines communes peuvent soutenir des objets que la majorité des autres communes de leur canton rejette, ou l’inverse. S’agit-il d’exceptions ponctuelles ou d’un comportement qui revient sur plusieurs votations ? Cette observation amène la seconde question : **quelles communes votent régulièrement à contre-courant du reste de leur canton, et pour quels thèmes ?** L’examen de ces écarts complète l’évaluation du modèle, sans utiliser le résultat cantonal du scrutin à prédire comme donnée d’entrée.

Ces analyses portent sur des résultats agrégés. Elles ne permettent pas d’attribuer un vote ou une motivation aux habitants d’une commune, ni d’établir une relation causale entre les caractéristiques du territoire et les choix exprimés.

## 2. Objectifs et périmètre

### Livrable obligatoire

1. Construire un jeu de données reproductible, avec une ligne par **commune et objet de votation**, à partir des résultats fédéraux officiels et d'une typologie territoriale des communes.
2. Classer les objets dans un petit nombre de thèmes documentés, sans utiliser leurs résultats pour choisir leur catégorie.
3. Explorer la part de « oui » et la participation selon la période, le thème et le territoire.
4. Comparer des références simples à au moins un modèle supervisé estimant la **part de « oui »** pour des scrutins historiques tenus à l'écart de l'entraînement.
5. Repérer les communes qui votent fréquemment dans le sens opposé au reste de leur canton, en indiquant le nombre d'objets qui étayent chaque constat.
6. Livrer une **application utilisable**, avec filtres, graphiques, comparaison entre valeurs observées et estimées, et explication des limites.

### Extensions

Une jointure démographique ou électorale supplémentaire ; un modèle distinct de participation ; un regroupement non supervisé des communes ; une carte interactive ; un indice de polarisation par objet ; une comparaison qualitative avec des analyses post-votation. Chaque extension fait l'objet d'une décision explicite fondée sur le temps restant et la qualité de la source. La météo du jour du scrutin n'est envisagée que si sa pertinence et sa disponibilité temporelle sont établies.

**Hors périmètre :** votations cantonales ou communales, prédiction nationale en direct, inférence sur les votes individuels et déploiement public en production.

## 3. Sources et préparation des données

La source principale est le [tableau historique de l'OFS des votations fédérales par commune depuis 1960](https://www.pxweb.bfs.admin.ch/pxweb/fr/px-x-1703030000_101/px-x-1703030000_101/px-x-1703030000_101.px/). Le [jeu JSON en temps réel cité dans l'énoncé](https://opendata.swiss/en/dataset/echtzeitdaten-am-abstimmungstag-zu-eidgenoessischen-abstimmungsvorlagen) peut servir à des vérifications ou à des essais, mais ne constitue pas, à lui seul, la source historique retenue. Le [répertoire officiel des communes](https://www.agvchapp.bfs.admin.ch/fr) fournit les codes et les typologies territoriales.

**Période de travail proposée : 2013–2024.** Elle sera confirmée après l'audit initial. Le tableau historique indique que ses résultats communaux sont harmonisés selon les communes au **1er janvier 2026** ; les communes spéciales, urnes communes, données absentes et écarts de référentiel restent à contrôler. Les résultats provisoires et les questions dont le sens du « oui » est ambigu sont exclus du socle, avec justification et décompte.

Les [données OFS de population par âge](https://opendata.swiss/en/dataset/standige-wohnbevolkerung-in-privathaushalten-nach-institutionellen-gliederungen-geschlecht-alte) et la [force des partis par commune](https://www.pxweb.bfs.admin.ch/pxweb/de/px-x-1702020000_105/px-x-1702020000_105/px-x-1702020000_105.px/) sont évaluées en semaine 4. Une source n'entre dans le modèle que si sa jointure est suffisamment fiable **et si sa valeur était disponible avant les scrutins prédits**. Sinon, son abandon est documenté ; l'application et le modèle restent livrables avec les données du socle.

La préparation contrôle les identifiants commune × objet, les doublons, les nombres de voix, les taux compris entre 0 et 1, les totaux et la couverture par canton et année. Un échantillon de totaux est rapproché de l'OFS. Le taux de réussite de chaque jointure et les exclusions sont publiés. La version et la date de collecte de chaque source sont conservées.

## 4. Analyse et modélisation

**Cible du modèle :** part de « oui » = `oui / (oui + non)` parmi les suffrages valables. La participation est calculée séparément selon la définition des champs OFS, vérifiée pendant l'audit. Les caractéristiques possibles sont le canton, la typologie territoriale, la date, le thème et les tendances de vote calculées uniquement à partir de scrutins **antérieurs**.

La taxonomie thématique comportera quelques catégories, par exemple environnement et énergie, finances, institutions, société et santé, transports, autre. Les cas incertains sont revus par un deuxième membre de l'équipe. On comparera :

- une **référence historique** fondée sur les votes antérieurs de la commune, avec repli sur des données antérieures du canton si nécessaire ;
- une **régression régularisée**, facile à interpréter ;
- un **modèle candidat sur arbres** si la validation montre qu'il apporte quelque chose.

Pour répondre à la première question, les mêmes scrutins et les mêmes métriques sont utilisés pour comparer un modèle fondé sur l'historique et le territoire à une version ajoutant le thème. L'importance des variables ou une méthode équivalente peut aider à décrire le modèle, mais **ne constitue pas une preuve de causalité**.

L'analyse « à contre-courant » compare, pour chaque objet, la majorité de la commune à celle des **autres communes de son canton**, obtenue en retranchant ses voix du total cantonal. Elle présente aussi l'écart de part de « oui », le nombre d'objets et la fréquence des majorités opposées par thème. On ne conclut pas à une tendance durable sur quelques cas isolés ; un minimum d'objets par thème est fixé après l'audit de couverture et avant la sélection des exemples.

### Validation sans fuite de données

| Ensemble | Découpage envisagé | Fonction |
|---|---|---|
| Entraînement | 2013–2021 | Apprentissage et calcul des historiques. |
| Validation | 2022 | Choix des variables, modèles et paramètres. |
| Test final | 2023–2024 | Évaluation après gel des choix. |

**Toutes les observations d'une même date de votation restent ensemble.** Aucun résultat de l'objet étudié, même agrégé au canton ou à la Suisse, ne sert à le prédire. Si la couverture de 2022 est insuffisante, le découpage de validation est revu *avant* l'examen du test. Les transformations et les historiques respectent l'ordre des dates.

La mesure principale est l'**erreur absolue moyenne sur la part de « oui »**, en points de pourcentage, calculée par objet puis moyennée entre objets. Les résultats comprennent aussi les erreurs par thème et canton, leur dispersion, et la comparaison avec chaque référence. La justesse de la majorité communale peut être ajoutée, avec prudence pour les cas proches de 50 %. Un modèle moins bon que sa référence reste présenté et discuté.

## 5. Application et critères de réception

L'application, développée avec des outils Python adaptés au projet, doit fonctionner localement sans service payant. Elle permet de choisir une date, un objet, un canton, une commune ou un thème ; de consulter les résultats et la participation ; de visualiser les écarts au reste du canton ; et de comparer les estimations **rétrospectives sur le test** aux valeurs observées. Elle indique la période d'entraînement, les définitions et les exclusions. Un extrait figé documenté garantit la démonstration même si le service source est indisponible.

Le projet est réceptionnable si :

| Critère | Preuve attendue |
|---|---|
| Le pipeline reconstitue les données et quantifie les exclusions et jointures non résolues. | Scripts relançables, contrôles et documentation. |
| Les ensembles temporels ne partagent aucune date et les caractéristiques ne contiennent aucun résultat courant. | Tests ciblés et revue des colonnes. |
| Les références et le modèle sont évalués sur les mêmes objets du test avec les métriques annoncées. | Tableau de résultats reproductible. |
| Les communes à contre-courant sont présentées avec leurs effectifs et les objets concernés. | Vue de l'application et description de la méthode. |
| Une personne autre que l'auteur du module peut installer et parcourir l'application. | Notice suivie lors d'une revue croisée. |

La qualité méthodologique et le fonctionnement de l'application constituent les critères de réussite ; aucun gain prédictif minimal arbitraire n'est promis.

## 6. Organisation et calendrier

Les quatre membres se répartissent les responsabilités **coordination**, **données**, **modélisation** et **application/qualité**. Chaque responsabilité reçoit un titulaire et un remplaçant distincts, inscrits dans le tableau de suivi du groupe. GitHub sert au code et aux revues ; Teams aux points hebdomadaires ; chaque membre tient le journal individuel demandé. Les conventions de code, de tests et de rédaction sont arrêtées au démarrage.

| Période indicative | Jalon et décision |
|---|---|
| Semaines 2–4 | Échantillon importé, audit des sources et des jointures ; décision **Go / No-Go** documentée pour chaque source supplémentaire. |
| Semaines 4–7 | Pipeline, thèmes, exploration, référence historique et première version fonctionnelle de l'application. |
| Semaines 8–10 | Comparaison des modèles, analyse des communes à contre-courant, intégration dans l'application. |
| Semaines 11–13 | Tests, relecture croisée, rapport et extensions uniquement si le socle est stable. |
| Semaines 14–16 | Remise et défense selon les dates officielles du cours. |

Le budget indicatif est de **120 heures par étudiant**, dont 64 heures encadrées et 56 heures personnelles. Une marge d'environ **12 heures par étudiant** couvre les difficultés d'extraction, de jointure et d'intégration ; elle n'est pas affectée d'avance aux extensions. Le tableau détaillé des heures et le planning du groupe complètent ce document.

**Risques principaux :** couverture inégale des sources externes, catégories thématiques ambiguës, fuite de données entre scrutins, modèle moins performant qu'une référence et intégration trop tardive. Les replis correspondants sont, respectivement, conserver le socle, regrouper les thèmes, tester le découpage temporel, publier les résultats défavorables et rendre l'interface utilisable dès le milieu du projet.

## 7. Livrables

- Une **application opérationnelle** et une notice d'installation et d'utilisation.
- Le dépôt contenant les scripts de préparation, l'entraînement, l'évaluation, les tests et les références des données ; remise électronique des sources et ressources sur Cyberlearn selon les consignes finales.
- Un **rapport principal unique en PDF**, concis et illustré, présentant les décisions, résultats, limites et contributions des membres.
- Les **journaux individuels**, le planning détaillé et une présentation orale à laquelle chaque membre participe.

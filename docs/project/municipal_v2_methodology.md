# Annexe méthodologique — modèle communal V2

Cette annexe décrit les choix d'apprentissage et d'évaluation. Les commandes
sont présentées dans [le guide V2](municipal_v2.md). Les résultats mesurés
appartiennent aux rapports d'expérience ; aucun score n'est présumé ici.

## Mesurer l'objectif de 4 points

La cible est la proportion de « oui » parmi les suffrages valables d'une
commune. Une MAE de **4 points de pourcentage** désigne une erreur absolue
moyenne, pas un plafond d'erreur pour chaque commune.

La métrique principale donne le même poids à chaque objet : calculer sa MAE
sur les communes, puis moyenner les MAE des objets. Les moyennes par ligne,
par date et les grandes erreurs complètent ce résultat. Une moyenne pondérée
par la population répond à une autre question et reste présentée séparément.

## Un pipeline appris sur l'entraînement

Pour Ridge et XGBoost, une `Pipeline` scikit-learn rassemble le prétraitement,
la sélection et le modèle. Un `ColumnTransformer` applique l'imputation
numérique par médiane, les indicateurs de valeurs manquantes, la
standardisation et l'encodage des catégories. Les catégories inconnues sont
traitées selon la configuration apprise. CatBoost dispose de son traitement
des catégories.

Les médianes, paramètres de normalisation, catégories et variables retenues
sont appris **dans chaque train**, puis appliqués à sa validation. La même
règle vaut pour une PCA ou un regroupement de communes. Ajuster ces étapes
sur l'ensemble des données permettrait à la validation d'influencer le
modèle, comme l'illustre la documentation sur les
[fuites de données](https://scikit-learn.org/stable/common_pitfalls.html).

`SelectKBest` utilise ici `f_regression`, un score univarié de dépendance
linéaire. Une variable utile seulement en interaction peut être écartée.
La variante qui conserve toutes les variables est donc une référence
nécessaire, et `k` est un paramètre à comparer en validation. La documentation
de [sélection de variables](https://scikit-learn.org/stable/modules/feature_selection.html)
distingue cette méthode des scores d'information mutuelle et des sélections
fondées sur un modèle.

## Prédire de nouveaux objets dans le temps

Les communes d'un même objet ne sont pas des observations indépendantes pour
mesurer la capacité à prédire un nouvel objet. Toutes les communes et tous
les objets d'une même date restent du même côté de chaque séparation.
L'entraînement précède strictement la fenêtre évaluée.

Les fenêtres de développement sont **2016–2018**, **2019–2020** et
**2021–2022**. Les historiques communaux sont calculés depuis le passé puis
figés au début de chaque fenêtre. Les résultats du premier scrutin d'une
fenêtre ne servent pas à prédire les suivants. Ce protocole combine les
principes de [validation temporelle et par groupes](https://scikit-learn.org/stable/modules/cross_validation.html).

**2023–2025 a déjà été exposé dans les travaux précédents.** Le gel de la
configuration avant sa comparaison V2 est utile pour la traçabilité, mais
ne transforme pas cette période en test indépendant. Les essais successifs
peuvent aussi finir par s'adapter aux fenêtres de développement. Une mesure
indépendante nécessite des résultats qui n'ont pas participé aux décisions,
par exemple des prévisions enregistrées avant de futurs scrutins.

## Recherche et journal des essais

[Optuna](https://optuna.readthedocs.io/en/stable/faq.html) explore des
configurations sur les seules fenêtres de développement et conserve son
état dans SQLite. Le nombre d'essais est explicite. Une amélioration se juge
sur plusieurs objets et périodes, avec une hypothèse identifiable : nouvelles
variables, autre profondeur historique, régularisation ou architecture.

Le suivi du projet repose sur les journaux JSON et les artefacts des essais :
configuration complète, hypothèse, dates des partitions, variables retenues,
métriques, durée, succès ou échec, versions des bibliothèques et empreintes
du code et des données. Les prédictions permettent de reproduire l'analyse
des erreurs. Ce dispositif est le suivi effectivement utilisé ; il ne suppose
pas un déploiement de MLflow. Le gel du candidat lie la sélection à ses
entrées, plutôt qu'au seul nom d'un fichier de modèle.

## Niveau de l'objet, différences locales et sondages

Le modèle hiérarchique apprend deux composantes : la moyenne des communes
pour un objet, et l'écart propre à chaque commune. Les métadonnées de l'objet
servent à prévoir la première ; les caractéristiques locales servent à
prévoir les écarts. Les moyennes et écarts observés ne sont calculés que sur
les objets d'entraînement. À l'inférence, la moyenne de l'objet est prédite ;
son résultat réel n'est pas fourni. Cette moyenne communale n'est pas le
résultat national pondéré par les suffrages.

Les sondages ajoutent une information différente, disponible seulement après
leur publication, généralement proche du scrutin. Une variante peut ajuster
les prédictions communales vers une estimation issue du sondage. Le poids de
cet ajustement et le traitement des indécis sont des choix de modèle à
évaluer. Un résultat obtenu avec les derniers sondages ne décrit pas la
qualité d'une prévision faite plusieurs mois auparavant.

Chaque sondage doit correspondre à l'objet exact et avoir été publié au plus
tard au cutoff `as_of`, avant le vote. L'ajustement utilise un lot communal
complet et un proxy démographique de l'électorat : population multipliée par
la part suisse et par la part hors 0–19 ans. Ce produit de marges ignore leur
dépendance, les électeurs de 18–19 ans, les expatriés et la participation.
Ce n'est ni un registre électoral ni le nombre de suffrages futurs.

## Place d'e-means et limites des sources

Le préprint [e-means, soumis le 6 novembre 2026](https://arxiv.org/abs/2611.09501),
présente une optimisation du clustering **k-means**. Il ne remplace pas kNN
et ne prédit pas directement une proportion de « oui ». Son usage éventuel
serait de construire des groupes ou distances entre communes. Il faudrait
les apprendre sur le train puis démontrer leur apport à la régression.
e-means n'est pas intégré aux modèles décrits ici.

L'extension depuis 1981 augmente la diversité des objets, mais conserve des
données anciennes manquantes et des dates de publication non attestées. La
géographie et les typologies fixes de 2026 limitent la reconstitution du passé.
Les directions déduites des titres sont des indices lexicaux avec abstention
sur les cas ambigus, pas des annotations juridiques validées. Un candidat
réentraîné sur tout l'historique reste donc un **modèle de recherche**, sans
garantie de précision ni validation de production.

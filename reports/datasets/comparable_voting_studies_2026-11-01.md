# Études comparables : prévoir les votations communales

Recherche du 1er novembre 2026. Sources primaires consultées sur le Web le même jour : articles originaux, dépôts institutionnels, code des auteurs et documentation des concepteurs. Aucun entraînement, aucune nouvelle mesure du dépôt et aucun accès au test 2023–2025.

## Ce qui aiderait le plus

**Les travaux EPFL suggèrent de modéliser la rencontre entre profil communal et contenu de l'objet.** Leurs scores pendant dépouillement ne sont toutefois pas transférables à une prévision sans résultats.

Le [rapport par blocs](block_selection_2026-11-01.md) montre des métadonnées d'objet instables selon les fenêtres et des typologies plus régulières, mais faiblement utiles. Cela motive d'autres représentations et interactions, sans démontrer leur efficacité.

## Trois tâches à ne pas confondre

| Régime | Informations sur le nouvel objet au moment de prévoir | Pertinence pour le projet |
| --- | --- | --- |
| Prévision avant vote | Texte, thèmes, recommandations et éventuellement sondages publiés avant le cutoff ; aucun résultat réalisé | Objectif principal ; sondages à traiter comme un régime supplémentaire |
| Prévision pendant dépouillement | Résultats d'une partie des communes du nouvel objet | Autre tâche ; excellente démonstration des structures territoriales, mais information interdite ici |
| Reconstruction rétrospective | Résultats du même objet dans d'autres territoires, parfois totaux contraints, ou ajustement sur l'ensemble de la matrice | Utile pour la géographie ou l'exploration ; aucune preuve de généralisation à un nouvel objet |

## Huit travaux et leurs limites

### 1. Etter, Khan, Grossglauser et Thiran — *Online Collaborative Prediction of Regional Vote Results* (DSAA, 2016)

C'est la comparaison suisse la plus proche : parts de oui pour **2 352 communes et 281 objets, 1981–2014**. Le modèle combine facteurs latents commune/objet, régression sur caractéristiques communales et recommandations de **13 partis**. Il comporte 25 caractéristiques communales. Les 231 premiers objets servent à l'apprentissage et les 50 derniers au test. La CV interne non bayésienne masque aléatoirement 10 % des cellules ; les auteurs reconnaissent qu'elle correspond à une généralisation « faible », mal adaptée au démarrage d'un objet inconnu.

Le papier rapporte une RMSE nationale inférieure à un point après révélation de 50 communes, avec ordres de révélation aléatoires. **Ce chiffre concerne le dépouillement, pas notre cible avant vote ni une MAE communale.** La branche utilisant les recommandations traite le démarrage sans résultats. Les dates historiques de publication des caractéristiques ne sont pas auditées comme dans notre V1 stricte ; les géographies manquantes sont interpolées.

**À transférer :** recommandations × profils communaux et facteurs historiques ; refaire la sélection des hyperparamètres sur objets futurs entiers. [Article original, sections II–IV et figures 3–4](https://indy.epfl.ch/grossglauser/Papers/dsaa2016_votepredict.pdf).

### 2. Immer, Kristof, Grossglauser et Thiran — *Sub-Matrix Factorization for Real-Time Vote Prediction* (KDD, 2020)

Le travail apprend par SVD une représentation territoriale historique, puis ajuste un GLM avec les résultats déjà révélés du nouvel objet. La Suisse comprend **330 objets et 2 196 communes**. L'évaluation suisse porte sur 26 objets et 100 ordres simulés chacun ; seuls les objets antérieurs entrent dans l'entraînement, y compris lorsque plusieurs objets partagent une date. Quatre objets de 2019–2020 sont également étudiés avec des résultats séquentiels réels. Des élections américaines et allemandes servent d'autres applications.

Les courbes nationales favorisent la méthode face à l'agrégation partielle naïve et à la factorisation de référence. Le papier reconnaît explicitement le **cold start** : au moins une observation du nouvel objet est nécessaire. Ne pas déduire une performance sans résultats ni remplacer ses courbes par un score communal inventé.

**À transférer :** compression historique et validation sur les prochains objets. **À ajouter pour notre tâche :** une fonction reliant le texte ou les recommandations au vecteur latent d'un nouvel objet. Cette extension reste notre hypothèse. [Article original](https://infoscience.epfl.ch/bitstreams/0b69b546-bd0a-4ba0-b608-5e51a6e747ea/download), [code des auteurs](https://github.com/indy-lab/predikon-lib).

### 3. Daniel Müller — brochures officielles et classification nationale (poster, 2019)

Le poster *A Comparison of Machine Learning Models to Predict the Outcome of Swiss Federal Votes Using the Text of the Official Voter Pamphlets* utilise le **texte allemand des brochures**. Il décrit 357 objets extraits début 2017, répartis en 303 d'entraînement et 54 de validation, puis un test de 14 objets de mai 2017 à novembre 2018. L'ordre ou le caractère aléatoire du premier partage n'est pas précisé.

La régression logistique atteint **92,9 %** d'exactitude sur ces 14 objets ; le CNN simple **100 %**. Il s'agit d'acceptation/rejet national, pas de parts de oui communales. Le poster précise que les réseaux ont été développés fin 2018 : leur score sur les objets 2017–2018 n'établit donc pas une prévision prospective publiée avant chacun des scrutins. Quatorze objets constituent un petit test.

**À transférer :** baseline textuelle simple, vocabulaire ajusté sur le train. **À ne pas transférer :** le score de classification comme promesse de MAE, ni une préférence automatique pour les réseaux profonds. [Poster original de l'auteur, méthodes et tableau 3](https://www.stellus.ch/wp-content/uploads/2019/01/11.3-Predicting-the-Outcome-of-Swiss-Federal-Votes_updated-20190127.pdf).

### 4. Jean-Luc Jucker — SwissRef, prévisions nationales sans sondages

SwissRef publie des prévisions nationales avant scrutin, sans sondages, avec parts de oui et probabilités d'acceptation. L'auteur décrit une comparaison de régressions, k-NN et forêts, une recherche d'hyperparamètres et de la CV. La page présente des prédictions datées et annonce, au 27 septembre 2026, **29 issues correctement prévues sur 36**, sur 13 sessions. Ce bilan est celui du concepteur ; les archives et horodatages n'ont pas été audités indépendamment ici.

La page ne fournit pas un protocole chronologique reproductible assez détaillé, une liste complète de variables et un code permettant de répliquer ces scores. Il est donc impossible d'attribuer le succès à un bloc précis ou de comparer équitablement à notre expérience.

**À transférer :** enregistrer publiquement une prévision figée, son cutoff et sa version avant le scrutin. **Limite :** cible nationale et modèle insuffisamment ouvert pour servir de référence répliquée communale. [Description, FAQ, historique et prédictions du concepteur](https://www.jeanlucjucker.net/swissref).

### 5. Etter, Herzen, Grossglauser et Thiran — *Mining Democracy* (COSN, 2014)

Cette étude suisse explore les profils territoriaux et cherche une commune représentative du résultat national. Pour la prédiction, elle utilise 245 objets : les **196 premiers** pour l'entraînement et **49 derniers** pour le test ; les classifieurs par commune sont réglés par CV sur le train. Le résultat **du même objet à Ebikon** permet de classifier correctement 47 des 49 issues nationales, soit **95,9 %**.

Ce résultat signifie qu'une commune observée peut résumer le résultat national ; il ne signifie pas que son vote a été prévu avant scrutin. C'est une transformation de résultat local disponible en issue nationale, avec une cible binaire. Les analyses de structure sont plus transférables que le score.

**À transférer :** des communes ou profils représentatifs peuvent aider à diagnostiquer les configurations territoriales. **À exclure comme prédicteur avant vote :** le résultat d'Ebikon ou de toute autre commune sur l'objet cible. [Article original, section 4.2 et figure 7](https://indy.epfl.ch/grossglauser/Papers/cosn2014_democracy.pdf).

### 6. John D. O'Brien — blocs latents dans les référendums du Maine (prépublication 2023 ; article 2026)

Le modèle de mélanges bayésiens examine **423 municipalités et 54 questions de 2008–2019**. Il estime le nombre de blocs, les profils de soutien par question et leurs mélanges municipaux. La formulation générale Dirichlet-multinomiale devient bêta-binomiale pour les totaux oui/non. Les blocs obtenus présentent une structure géographique et une certaine stabilité ; des questions à portée locale sont moins bien décrites par la structure commune.

L'objectif principal est l'inférence de structure, avec vérifications prédictives postérieures sur les données observées et analyses par périodes. **Ce n'est pas un benchmark de prévision chronologique d'une question entièrement inconnue.** Aucune MAE de ce type n'est revendiquée ici.

**À transférer :** profils latents et analyse des objets qui échappent aux clivages habituels. Inférer ces profils uniquement sur le passé, puis apprendre séparément comment le nouvel objet active les blocs. Ne pas interpréter ces blocs agrégés comme des votes individuels identifiés. [Prépublication de l'auteur](https://arxiv.org/abs/2301.01677), [article original publié](https://www.cambridge.org/core/journals/political-science-research-and-methods/article/bayesian-mixture-model-captures-temporal-and-spatial-structure-of-voting-blocs-within-longitudinal-referendum-data/B2C9A113D969277325F9EDAC4F90E83F).

### 7. Blumenau, Lauderdale, Bailey et Rivers — MRP avant élections et Brexit (2020)

*Model-Based Pre-Election Polling for National and Sub-National Outcomes in the US and UK* décrit des prévisions **publiées avant** Brexit 2016, l'élection présidentielle américaine 2016 et les élections britanniques 2017. Le système combine sondages contemporains, recensement et historique avec régression multiniveau, participation et poststratification.

Pour Brexit, le tableau 2 donne **50,6 % Leave prévus contre 51,9 % réalisés**, avec intervalle de 95 % [48,8 ; 52,4]. Les parts locales sont corrélées aux résultats à **r = 0,92**. Cette corrélation ne mesure pas une MAE et ne garantit pas une bonne calibration. 

**À transférer :** distinguer niveau national et variations locales, partager l'information entre territoires et examiner la participation. **Obstacle :** les sondages individuels et les cellules de poststratification requises ne sont pas nos simples marges STATPOP ; une régression agrégée n'est pas automatiquement du MRP. [Manuscrit accepté, sections 4–5, tableau 2](https://discovery.ucl.ac.uk/id/eprint/10074013/1/ijf_final_submission.pdf), [notice institutionnelle](https://discovery.ucl.ac.uk/id/eprint/10074013/).

### 8. Chris Hanretty — *Areal interpolation and the UK's referendum on EU membership* (2017)

Ce travail reconstruit les résultats Brexit par circonscription à partir des résultats **déjà connus par autorité locale**. Des régressions de Poisson sur les comptes Leave et Remain utilisent les caractéristiques démographiques ; les prédictions sur les intersections géographiques sont recalées pour respecter les totaux observés avant réagrégation.

**Pertinence :** exemple précis de différence entre reconstruire une géographie et prévoir un scrutin. Une estimation très précise peut exploiter les totaux du même vote ; elle ne résout pas le problème d'un objet futur. Le manuscrit consulté ne fournit pas de score de prévision avant vote applicable à notre cible, et aucun n'est déduit ici.

**À transférer :** documenter les transformations territoriales et les contraintes de total si une reconstruction est nécessaire. Conserver ces résultats comme données reconstruites, avec leur incertitude, sans les présenter comme des observations communales originelles. [Manuscrit original de l'auteur](https://chrishanretty.co.uk/pubs/10.1080_17457289.2017.1287081/fulltext.pdf), [notice universitaire](https://research-portal.uea.ac.uk/en/publications/areal-interpolation-and-the-uks-referendum-on-eu-membership/).

## Trois expériences proposées, par ordre de priorité

Les propositions suivantes sont des **choix pour ce dépôt**, pas des résultats déjà démontrés dans ces articles.

**Diagnostic de spécification du dépôt :** les comparaisons du rapport par blocs concernent un Ridge additif. Sans croisements explicites entre objet et commune, le modèle ne peut pas faire varier librement le contraste entre deux profils communaux selon le thème. Cela motive des interactions ; cela ne prouve pas qu'elles amélioreront la validation. Le manuscrit MRP constate aussi que ses variantes additives sans interactions de contexte politique fonctionnaient moins bien dans ses essais : analogie utile, dans un autre régime de données ([section 5.2](https://discovery.ucl.ac.uk/id/eprint/10074013/1/ijf_final_submission.pdf)).

### 1. Interactions objet × profil communal

Comparer des croisements limités thème × langue/typologie/parts partisanes avec le Ridge actuel. Puis construire un score d'alignement : somme des forces communales des partis recommandant oui, avec scores séparés pour non, liberté de vote et information absente. Les élections doivent précéder le cutoff ; les consignes doivent être publiées avant celui-ci. Une consigne ne représente pas le vote de tous les électeurs du parti.

Comparer historique seul, consignes seules ajoutées, profils partisans ajoutés et interactions. Tester HistGradientBoosting à réglage fixé sur les mêmes fenêtres comme comparateur. **Pourquoi :** les ablations actuelles ne testent pas si une information communale devient utile conditionnellement au thème. Régulariser, limiter les interactions et stabiliser les correspondances de partis.

### 2. Analogues textuels, niveau général et écarts locaux

Réutiliser [text_votes.py](../../scripts/modeling/text_votes.py), dont la concaténation Ridge reste additive, et les règles de [forecast_text_export.md](../../docs/project/forecast_text_export.md). Comparer TF-IDF et moyenne des résultats d'objets antérieurs pondérée par similarité avec la brochure du nouvel objet. Ajuster le vocabulaire sur le train, isoler chaque objet dans la brochure et documenter les langues.

Prédire séparément le niveau général de soutien et les écarts communaux, ceux-ci appris sur les objets passés similaires. **Jamais le résultat national du nouvel objet dans les entrées.** L'objectif est de distinguer popularité générale et réaction territoriale. Les milliers de lignes communales répétant un texte ne deviennent pas des milliers d'objets indépendants.

### 3. Facteurs historiques conditionnés par l'objet

Apprendre une petite représentation des communes dans la matrice des résultats passés, éventuellement recentrée par niveau national historique. Relier ensuite métadonnées/recommandations/texte à la réponse sur ces facteurs avec une fonction régularisée. Comparer à l'expérience 1 et à une variante sans facteurs.

**Pourquoi en troisième :** les représentations EPFL sont proches, mais identifier un objet sans aucune commune dépouillée demande un pont supplémentaire à valider. Régler la dimension dans des fenêtres internes, reconstruire les facteurs dans chaque train et documenter communes absentes et mutations. PCA/SVD représente ici l'historique ; ce n'est pas un classement d'importance de la démographie.

## Protocole minimal

- Commencer sur les fenêtres 2016–2020 déjà explorées, avec les mêmes clés et historiques. Réserver 2023–2025 ; la validation 2021–2022 déjà exposée n'est plus une confirmation indépendante.
- Garder tous les objets d'une date ensemble, avec train strictement antérieur. Ajuster vocabulaire, SVD, imputations, sélection et hyperparamètres dans les trains ; régler sur des objets futurs entiers dans des fenêtres internes. Un masque aléatoire de cellules teste autre chose.
- Rapporter MAE communale, moyenne par objet/date et gains appariés ; distinguer métriques nationales, pondérées et classification. Examiner séparément erreur générale d'un objet et contrastes territoriaux.
- Conserver l'étiquette rétrospective exploratoire tant que publications historiques et géographie admissible ne sont pas prouvées. Une meilleure architecture ne résout pas ces limites de données.

## Portée de la recherche

Recherche ciblée, sans prétention d'exhaustivité. Aucun travail vérifié ici ne démontre déjà un modèle ouvert sans sondage ni résultat partiel battant notre référence sur la même cible communale et des dates futures entières.

L'[annonce de projet INDY/EPFL](https://indy.epfl.ch/project/36) vise l'extension de Predikon à l'avant-vote par brochures et métadonnées : rapprochement direct, mais pas performance achevée publiée. La [documentation Predikon](https://www.predikon.ch/en/about) confirme l'usage de résultats communaux dès midi le jour du vote.

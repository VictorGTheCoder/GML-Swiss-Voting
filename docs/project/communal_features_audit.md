# Audit des caractéristiques communales candidates

**Projet :** GML — analyse et prédiction des votations fédérales suisses
**Périmètre :** partie 2, inventaire des caractéristiques décrivant les communes
**Date de l'audit :** 2026-09-29
**Branche :** `2-audit-features-communales`

## 1. Conclusion opérationnelle

Un socle réaliste existe auprès de l'OFS et des organismes fédéraux :

1. population résidante permanente, avec un retard temporel explicitement documenté ;
2. structure par âge construite à partir du même cube STATPOP ;
3. densité calculée à partir de STATPOP et d'une surface communale cohérente avec l'état des communes ;
4. région linguistique OFS, en utilisant la version publiée avant la date de chaque votation ;
5. force électorale issue de l'élection au Conseil national précédente ;
6. une typologie territoriale OFS, seulement si sa version et sa date de disponibilité sont respectées.

Ces données sont des **candidate features**. Cet audit ne mesure ni leur pouvoir explicatif ni leur utilité prédictive. Une validation temporelle, des ablations et une analyse d'erreurs seront nécessaires ultérieurement.

Le principal risque n'est pas l'absence de données, mais l'utilisation rétrospective de valeurs actuellement disponibles. Une table mise à jour en 2026 ne peut pas être appliquée sans précaution aux votations de 2013 à 2025. La future intégration devra conserver, pour chaque observation, au minimum :

- la date du scrutin ;
- l'année de référence de la statistique ;
- la date ou la version de publication connue à cette date ;
- l'état des communes utilisé ;
- le numéro OFS de commune et, si nécessaire, la table de correspondance historique.

## 2. Règle d'audit temporel

Une feature est ex ante si la valeur et sa publication auraient été disponibles avant le scrutin prédit. La date de référence statistique seule ne suffit pas : une donnée 2020 publiée en 2022 est une donnée historique, mais elle n'était pas disponible pour un scrutin de 2021.

La stratégie recommandée pour la suite est une jointure « as-of » : pour une votation à la date `t`, sélectionner la dernière observation dont la date de publication vérifiée est antérieure à `t`. En l'absence d'archive de publication, appliquer une règle conservatrice documentée (par exemple année `t-1`) et marquer la valeur comme approximation. Il ne faut pas prendre aveuglément la dernière valeur du cube actuel.

Les catégories utilisées dans la colonne **Temporalité** sont :

- **bonne** : série suffisamment fréquente et mécanisme ex ante clair ;
- **utilisable sous conditions** : source exploitable, mais version, retard, révision ou couverture à contrôler ;
- **problématique** : la valeur actuelle ne représente pas correctement la situation historique ;
- **inconnue** : date de publication ou historique non vérifié.

## 3. Tableau central de présélection

| Feature / famille | Source officielle et dataset | Granularité / jointure | Années / fréquence | Historique fiable | Ex ante | Risque fuite | Coût intégration | Statut |
|---|---|---|---|---|---|---|---|---|
| Population totale | OFS, STATPOP, `px-x-0102010000_101` | Commune ; numéro OFS à conserver, pas le nom | 2010–2025 ; annuelle, référence 31 décembre | Bonne pour les séries, état communal de diffusion à contrôler | Oui avec version publiée avant `t` ; règle conservatrice `t-1` possible | Faible si la date de publication est connue ; moyen si l'on utilise le cube 2026 sans archive | Faible | **PRIORITAIRE** |
| Structure par âge | OFS, STATPOP, `px-x-0102010000_103` ou `px-x-0102010000_101` | Commune ; numéro OFS | 2010–2025 ; annuelle, âge détaillé ou classes d'âge | Bonne pour les années disponibles ; regroupements à figer | Oui sous la même règle as-of que la population | Moyen : révisions et géographie harmonisée | Faible | **PRIORITAIRE** |
| Part étrangère / nationalité | OFS, STATPOP, `px-x-0102010000_101` | Commune ; numéro OFS | 2010–2025 ; annuelle | Bonne, mais définition de la population à préciser | Oui sous condition de publication antérieure | Faible à moyen | Faible | **OPTIONNEL** |
| Densité | Population STATPOP + surface AREA / limites GEOSTAT ou `swissBOUNDARIES3D` | Commune ; numéro OFS commun aux deux sources | Population annuelle ; surface par campagnes ou état de limites | Utilisable sous conditions : surface non annuelle dans AREA et mutations territoriales | Oui si surface et population sont antérieures à `t` | Moyen : division par une surface contemporaine ou changement de périmètre | Moyen | **À INVESTIGUER** |
| Typologie urbain-rural / typologie des communes | OFS, Niveaux géographiques de la Suisse ; versions 2012 et 2020 | Commune ; numéro OFS / état des communes de la version | Versions, pas une série annuelle ; 9 ou 25 catégories, et urbain/intermédiaire/rural | Bonne par version, mais chaque version décrit une période différente | Version 2012 pour les scrutins postérieurs à sa publication ; version 2020 seulement après sa publication | Élevé si la typologie 2020 est appliquée aux scrutins antérieurs | Faible à moyen | **PRIORITAIRE** |
| Agglomération / centre / couronne | OFS, agglomérations et espace à caractère urbain | Commune ; état communal de la version | Versions 2012 et 2020 ; mises à jour selon nomenclature | Utilisable sous conditions ; les périmètres changent | Oui seulement avec la version disponible à `t` | Élevé en rétrospectif | Moyen | **À INVESTIGUER** |
| Région linguistique | OFS, nomenclature « Régions linguistiques » ; versions 2017 et 2022 | Commune ; rattachement OFS, avec table historique | Version 2017 basée sur RS 2010–2014 ; version 2022 sur RS 2016–2020 ; révision environ tous les 5 ans depuis 2017 | Bonne par version ; ce n'est pas une vérité fixe de tous les temps | Oui si la version publiée avant `t` est utilisée ; éviter la version 2022 pour les scrutins antérieurs à 2022 | Moyen si version actuelle appliquée au passé | Faible | **PRIORITAIRE** |
| Force des partis | OFS, élections au Conseil national, `px-x-1702020000_105` | Commune/district ; vérifier le code OFS dans l'export et exclure les communes spéciales | 1971–2023 ; élection nationale, environ tous les 4 ans ; 25 partis et % | Bonne, mais résultats harmonisés à un état communal récent | Oui : dernière élection nationale antérieure au scrutin prédit | Moyen : harmonisation, partis fusionnés, urnes communes | Moyen | **PRIORITAIRE** |
| Taille des ménages | OFS, STATPOP, `px-x-0102020000_401` | Commune ; numéro OFS | 2012–2023 ; annuelle, 31 décembre | Bonne pour ménages privés, mais référence spatiale 2023 | Oui sous règle de publication as-of | Faible à moyen | Faible | **OPTIONNEL** |
| Emploi et structure économique | OFS, STATENT, `px-x-0602010000_102` | Commune ; numéro OFS ; emplois au lieu de travail | 2011–2024 ; annuelle, période de référence décembre | Bonne pour l'activité locale ; révisions et confidentialité possibles | Oui si l'année publiée est antérieure au scrutin | Moyen : publication différée, `X` pour protection des données, lieu de travail ≠ domicile | Moyen | **OPTIONNEL** |
| Formation | OFS, Relevé structurel ; cubes City Statistics examinés | Principalement villes/agglomérations dans les cubes trouvés, pas un socle communal national confirmé | 2010–2020/2021 selon cube ; annuelle mais échantillonnée et parfois poolée | Insuffisante pour toutes les communes ; estimations et ruptures méthodologiques | Possible pour les zones couvertes, sous conditions | Moyen à élevé : publication différée, petits effectifs, changements de questionnaire | Élevé | **À ÉCARTER** |
| Revenu / chômage | OFS City Statistics, SECO pour le chômage | Cubes publics examinés surtout villes/agglomérations ; pas de table communale nationale confirmée dans cet audit | Périodes hétérogènes ; mensuel ou annuel selon source | Insuffisante pour un socle homogène de toutes les communes | À étudier source par source | Moyen à élevé | Élevé | **À INVESTIGUER** |
| Religion | OFS / relevés statistiques, selon agrégation | Granularité et disponibilité communale historique non établies | Hétérogène | Inconnue dans le périmètre de cet audit | Inconnue | Élevé, notamment confidentialité et sensibilité | Élevé | **À ÉCARTER** |

## 4. Audit détaillé des sources

### 4.1 Typologie territoriale

**Source.** L'OFS publie la « Typologie des communes et typologie urbain-rural 2020 » dans les Niveaux géographiques de la Suisse. La version 2020 comprend une typologie en 9 catégories, une typologie en 25 catégories et trois catégories urbain/intermédiaire/rural. Les critères combinent densité, taille, accessibilité et éléments socio-économiques.

**Période et disponibilité.** La version 2020 est calculée avec STATPOP 2019–2021, STATENT 2019–2021, HESTA et matrices de pendularité 2018/2020. Les résultats sont présentés à l'état communal du 1er janvier 2024. Elle est donc utile pour un modèle prospectif contemporain, mais elle ne peut pas être injectée rétroactivement dans des votations antérieures à sa disponibilité. La version 2012 est la candidate historique à examiner pour la période précédente ; la date exacte de publication doit être conservée avec la donnée.

**Jointure et mutations.** Utiliser le numéro OFS et l'état des communes de la version, jamais le nom. La typologie est un outil de classification par version, pas une observation annuelle. Une analyse historique doit soit conserver la version connue à chaque date, soit assumer explicitement une feature statique et mesurer la sensibilité à ce choix.

**Intérêt et coût.** Très bon rapport intérêt/coût pour réduire la dimension du territoire à quelques catégories. Le coût technique est faible une fois la bonne version récupérée ; le coût méthodologique est la gestion des versions.

### 4.2 Population, âge et nationalité

**Source exacte.** Le cube STATPOP `px-x-0102010000_101` couvre la population résidante permanente et non permanente par année, canton/district/commune, type de population, nationalité, sexe et âge. La page consultée indique des années 2010–2025, une référence au 31 décembre, une granularité communale et une référence spatiale actuelle « communes / 06.04.2025 ». Le cube `px-x-0102010000_103` offre aussi le sexe, l'état civil et la classe d'âge. Le cube `px-x-0102020000_401` fournit les ménages privés par taille pour 2012–2023.

**Features possibles.** À partir des effectifs par âge, construire des parts plutôt que des comptes bruts : moins de 20 ans, 20–39, 40–64 et 65 ans ou plus, ou des classes OFS directement disponibles. Le choix final des groupes doit être figé avant l'évaluation et appliqué uniformément. L'âge moyen ou médian n'est pas nécessaire si les groupes sont disponibles.

**Temporalité.** La fréquence annuelle est adaptée à une stratégie as-of. Le jour de référence est le 31 décembre : pour une votation du 23 septembre 2018, une valeur 2018 n'est pas une valeur connue à la date du vote, même si elle existe aujourd'hui ; une valeur 2017 est un choix conservateur à vérifier contre la date de publication. Les révisions du cube actuel ne remplacent pas une archive de publication.

**Définition.** Il faut choisir dès le départ entre population résidante permanente et population totale/permanente + non permanente. La première est plus stable pour l'âge et les ménages ; la seconde peut être pertinente pour certains contextes, mais elle comporte des cas non attribués à une commune dans le domaine de l'asile. Cette décision relève de la spécification future, pas d'une conclusion de cet audit.

### 4.3 Densité et surface

**Source.** L'OFS propose AREA (`px-x-0202020000_101`) avec des périodes de couverture du sol 1979–1985, 1992–1997, 2004–2009, 2013–2018 et 2020–2025. Les limites administratives et les surfaces communales sont aussi disponibles via GEOSTAT / swisstopo, notamment `swissBOUNDARIES3D`, qui porte le numéro OFS.

**Construction.** La densité de population est calculable comme `population / surface communale`, en documentant l'unité et le traitement des lacs. Il faut préférer la surface totale cohérente avec le référentiel géographique choisi et non une surface actuelle appliquée à toutes les années.

**Limite.** AREA n'est pas annuelle : une surface 2013–2018 ne doit pas être présentée comme une mesure exacte de chaque année. Pour les fusions, une surface d'une commune actuelle peut être incompatible avec les résultats électoraux qui existaient avant la fusion. Le statut reste donc « À INVESTIGUER » jusqu'à la vérification d'un petit échantillon couvrant les principales mutations du projet.

### 4.4 Région linguistique

**Source et méthode.** L'OFS détermine la région linguistique au niveau communal selon la langue nationale majoritaire. La version publiée en 2017 repose sur les relevés structurels poolés 2010–2014 et l'état communal du 1er janvier 2017. La version publiée en 2022 repose sur les relevés structurels poolés 2016–2020. Depuis 2017, l'actualisation est prévue environ tous les cinq ans ; les communes issues de mutations peuvent être réévaluées.

**Utilisation.** La version 2017 est une bonne candidate pour les scrutins postérieurs à sa publication ; la version 2022 ne doit pas être rétro-projetée sur des scrutins antérieurs. Pour les premières votations de la période du projet, il faut soit utiliser une version antérieure (par exemple la nomenclature issue du recensement 2000), soit déclarer la feature indisponible pour ces dates.

**Point conceptuel.** Une attribution majoritaire ne représente pas toutes les communes bilingues. Par exemple, l'OFS donne une seule région majoritaire à une commune même si plusieurs langues sont importantes. Il faut conserver la catégorie OFS et ne pas la renommer abusivement en « langue officielle ».

### 4.5 Force électorale des partis

**Source.** Le cube OFS `px-x-1702020000_105`, « Elections au Conseil national (suffrages des partis et force des partis depuis 1971 : districts et communes) », fournit des suffrages et des pourcentages au niveau communal/district. La page consultée indique 14 années et 25 partis, avec les années récentes 2015, 2019 et 2023.

**Features candidates.** Pour chaque parti ou famille de partis, utiliser le pourcentage de force électorale à la dernière élection nationale strictement antérieure à la votation. Une compression en quelques familles peut être étudiée plus tard ; elle ne doit pas être décidée pendant cet audit. Une feature « distance depuis la dernière élection » peut aussi être dérivée, mais ce sera une décision du futur pipeline.

**Exemple temporel.** Pour une votation du 23 septembre 2018, l'élection fédérale de 2015 est admissible ; celle de 2019 ne l'est pas. Pour une votation de 2020 ou 2021, 2019 est admissible. Le mécanisme sera à implémenter plus tard, avec un test automatique empêchant toute élection postérieure à la date cible.

**Limites documentées par l'OFS.** Les résultats sont harmonisés à un état communal récent afin de faciliter les comparaisons. Des communes ont partagé une urne, certaines valeurs sont inconnues, les mutations de canton peuvent rendre les nombres de voix non comparables et les partis ont changé de regroupement (par exemple PRD/PLS et PDC/PBD). Pour le modèle, utiliser les pourcentages et documenter les regroupements ; exclure les communes spéciales et les cas sans interprétation claire.

### 4.6 Emploi, structure économique et ménages

La STATENT `px-x-0602010000_102` fournit, par commune, année, secteur économique et unité d'observation, le nombre d'établissements, d'emplois et d'équivalents plein temps. La couverture consultée va de 2011 à 2024, avec période de référence en décembre et état communal au 1er janvier 2024. C'est une bonne candidate d'enrichissement pour la structure économique, mais elle décrit les emplois au lieu de travail, pas la composition des habitants. Les cellules `X` sont masquées pour raisons de protection des données et la diffusion est susceptible d'être décalée.

La taille des ménages est disponible dans STATPOP `px-x-0102020000_401`, de 2012 à 2023. Elle paraît plus simple à intégrer que la formation ou le revenu et peut fournir, par exemple, la part des ménages d'une personne ou des tailles moyennes. Le cube devra toutefois être vérifié pour la couverture des petites communes et le traitement des fusions.

### 4.7 Formation, revenu et chômage

Le Relevé structurel est pertinent en théorie, mais les cubes officiels trouvés dans l'audit concernant la formation et le revenu/travail sont surtout ceux de City Statistics, limités à des villes ou agglomérations. Les estimations sont issues d'un échantillon, doivent être accompagnées d'un intervalle de confiance et certaines années ne sont plus directement comparables après des changements de questionnaire ou de pondération. Ils ne constituent donc pas, à ce stade, un socle national communal robuste.

Le SECO publie bien des statistiques du marché du travail et l'OFS publie des indicateurs nationaux ou urbains, mais une table historique communale complète avec dénominateur et date de publication ex ante n'a pas été confirmée dans cette passe. Il ne faut pas reconstituer un taux de chômage communal en mélangeant un numérateur actuel et une population active issue d'une autre année. Ces familles restent à investiguer séparément.

La religion n'est pas retenue dans le socle initial : la couverture communale et historique n'a pas été établie ici et la variable est sensible. Son éventuelle utilisation demanderait une justification agrégée, éthique et statistique spécifique.

## 5. Identifiants et communes historiques

Le référentiel à utiliser est le **numéro OFS de commune**. L'application officielle des communes suisses fournit l'état des communes, le répertoire historisé, les annonces de mutation et les services REST. Elle indique explicitement que l'OFS attribue et gère le numéro officiel de chaque commune.

Règles de jointure à respecter :

1. stocker l'identifiant comme chaîne, car des représentations avec zéros initiaux existent dans les fichiers du projet ;
2. ne jamais joindre sur le nom seul ;
3. conserver `valid_from`, `valid_to` ou équivalent pour les états communaux ;
4. signaler les communes spéciales de la statistique politique, les urnes communes et les territoires non attribués ;
5. vérifier si chaque export PXWeb fournit le numéro dans une colonne séparée ou seulement dans le libellé ;
6. distinguer une réaffectation harmonisée à une géographie récente d'un résultat effectivement observé dans la commune historique.

Le répertoire historisé indique notamment les règles de numérotation : un changement de nom sans changement de territoire conserve généralement le numéro ; une scission reçoit de nouveaux numéros ; une fusion peut conserver le numéro d'une commune ou recevoir un nouveau numéro selon le type de mutation ; un changement de canton peut également entraîner un nouveau numéro. Cette logique suffit pour construire une table de correspondance, mais sa construction complète est hors périmètre de cette branche.

## 6. Socle recommandé pour la prochaine phase

À tester en premier, avec une table de versions :

- typologie territoriale OFS, en séparant clairement les versions 2012 et 2020 ;
- population résidante permanente ;
- parts par groupes d'âge ;
- région linguistique OFS historique disponible à la date cible ;
- force des partis à l'élection fédérale précédente.

La densité doit rejoindre ce socle après validation de la surface et du référentiel communal. La part étrangère est un enrichissement peu coûteux, mais doit rester distincte de la population totale afin d'éviter une redondance non maîtrisée.

## 7. Enrichissements potentiels

- densité et parts de surface bâtie/agricole après vérification de AREA ;
- taille des ménages STATPOP ;
- emplois, équivalents plein temps et parts sectorielles STATENT ;
- agglomération/centre/couronne avec une version historique ;
- formation si une table communale nationale avec historique, incertitudes et publication ex ante est confirmée ;
- revenu ou chômage si une source communale complète et temporellement exploitable est identifiée.

## 8. Données à éviter dans le socle initial

- typologie 2020 appliquée aux votations antérieures à sa publication ;
- région linguistique 2022 appliquée à toutes les votations depuis 2013 ;
- snapshot communal 2026 utilisé comme état historique ;
- agrégats de formation ou revenu City Statistics extrapolés aux communes non couvertes ;
- données dont le code communal n'est pas vérifiable ;
- caractéristiques calculées à partir de résultats électoraux postérieurs à la votation cible ;
- variables sensibles ou très incomplètes sans justification spécifique.

## 9. Questions ouvertes avant intégration

1. Quelles sont les dates de publication historiques des millésimes STATPOP, STATENT et des versions de nomenclature ?
2. Les exports PXWeb retenus exposent-ils le numéro OFS dans un champ séparé, et sous quel type ?
3. L'état communal harmonisé des résultats de votation est-il le même que celui de STATPOP et des élections nationales pour chaque période ?
4. Faut-il reconstruire les features dans la géographie de chaque scrutin ou dans une géographie harmonisée commune ?
5. Quelle version de la région linguistique est disponible avant les premières votations du périmètre ?
6. Peut-on obtenir une surface communale historique fiable pour les années de fusion importantes, ou faut-il exclure les observations concernées ?
7. Quel délai de publication doit être adopté pour une donnée annuelle dont la date de diffusion n'est pas archivée ?
8. Une source officielle communale complète existe-t-elle pour la formation, le revenu et le chômage, au-delà de City Statistics ?
9. Quelle règle de regroupement des partis reste stable malgré les fusions et changements de nom ?
10. Comment traiter les communes partageant une urne et les communes spéciales dans le dataset de votation ?

## 10. Sources examinées

| Organisme | Source / dataset | URL ou identifiant | Format / remarque |
|---|---|---|---|
| OFS | STATPOP population, nationalité, sexe, âge | [`px-x-0102010000_101`](https://www.bfs.admin.ch/asset/fr/px-x-0102010000_101) | Cube PXWeb ; personne ; commune ; 2010–2025 |
| OFS | STATPOP âge et état civil | [`px-x-0102010000_103`](https://www.bfs.admin.ch/asset/fr/px-x-0102010000_103) | Cube PXWeb ; personne ; commune ; 2010–2025 |
| OFS | Ménages privés par taille | [`px-x-0102020000_401`](https://www.bfs.admin.ch/asset/fr/px-x-0102020000_401) | Cube PXWeb ; personne/ménage ; 2012–2023 |
| OFS | Bilan démographique | [`px-x-0102020000_201`](https://www.bfs.admin.ch/asset/fr/px-x-0102020000_201) | Cube PXWeb ; utile pour contrôles de cohérence |
| OFS | Statistique suisse de la superficie AREA | [`px-x-0202020000_101`](https://www.bfs.admin.ch/asset/fr/px-x-0202020000_101) | Cube PXWeb ; hectares ; périodes pluriannuelles |
| OFS / swisstopo | Limites communales et surfaces | [swissBOUNDARIES3D](https://www.swisstopo.admin.ch/fr/limites-cantonales-et-communales) | Données géographiques ; mise à jour annuelle ; numéro OFS |
| OFS | Typologie des communes et typologie urbain-rural 2020 | [Swiss Stats Explorer](https://www.swissstats.bfs.admin.ch/data/webviewer/appId/ch.admin.bfs.swissstat/article/issue242122982000-05/package) | Nomenclature versionnée ; 9/25 types et urbain/intermédiaire/rural |
| OFS | Régions linguistiques | [Fiche signalétique](https://dam-api.bfs.admin.ch/hub/api/dam/assets/23887726/master) ; [version 2017](https://www.bfs.admin.ch/bfsstatic/dam/assets/415725/master) | Nomenclature communale ; versions 2017 et 2022 |
| OFS | Régions linguistiques par commune, version 2020 | [Atlas statistique](https://www.atlas.bfs.admin.ch/maps/13/fr/17138_17137_235_227/26599.html) | Carte et export Excel ; état 2022 |
| OFS | Elections au Conseil national, force des partis | [`px-x-1702020000_105`](https://www.bfs.admin.ch/asset/fr/px-x-1702020000_105) | Cube PXWeb ; commune/district ; 1971–2023 ; % et suffrages |
| OFS | STATENT établissements et emplois par secteur | [`px-x-0602010000_102`](https://www.bfs.admin.ch/asset/fr/px-x-0602010000_102) | Cube PXWeb ; commune ; 2011–2024 ; emplois/EPT/établissements |
| OFS | City Statistics formation | [`px-x-2105000000_201`](https://www.bfs.admin.ch/asset/fr/px-x-2105000000_201) | Cube PXWeb ; villes/agglomérations ; échantillonnage |
| OFS | City Statistics revenu et travail | [`px-x-2105000000_203`](https://www.bfs.admin.ch/asset/fr/px-x-2105000000_203) | Cube PXWeb ; villes/agglomérations ; couverture limitée |
| SECO | Statistiques du marché du travail | [Page SECO](https://www.seco.admin.ch/fr/statistiques-marche-travail) | Données marché du travail ; granularité communale à confirmer |
| OFS | Répertoire officiel et historisé des communes | [Application des communes suisses](https://www.agvchapp.bfs.admin.ch/fr) | XLSX, XML/TXT historisés, REST ; référentiel des numéros OFS |
| OFS | Résultats des votations fédérales, contexte de jointure | [`px-x-1703030000_101`](https://www.bfs.admin.ch/asset/fr/px-x-1703030000_101) | Cube PXWeb ; résultats communaux ; source déjà utilisée par le projet |

## 11. Fichiers et périmètre de cette branche

Fichier créé par cette tâche :

- `docs/project/communal_features_audit.md`

Aucun dataset brut n'a été ajouté et aucun pipeline, modèle ou dataset `commune × votation` n'a été modifié dans le cadre de cet audit.

# V13 — nouvelles sources indépendantes (25 novembre 2026)

Suite de [V10](../v10_campaign/README.md), [V11](../v11_campaign/README.md), [V12](../v12_campaign/README.md). Meilleur exploratoire V11.3 : 6,955753873756506 pp, 66 objets/23 dates/138868 lignes 2016–22 ; V8.1 gelée 7,229527497606818, V9 historique 7,131910681945383. V12.4 : meilleur nouveau mélange 6,9705, aucun gain. V12.2 différée (provenance). Aucun accès au holdout, aucune promotion.

## V13.1 — audit de faisabilité APS

La base d'annonces de presse APS (Université de Berne) est distincte des rapports de tonalité éditoriale fög V10.2. Le codebook du 08.03.2026 indique des observations depuis 2013, dates de publication et identifiants, licence CC BY (données), CC0 (codebook), DOI [10.48620/98224](https://doi.org/10.48620/98224). Les pages 2–3 ont été vérifiées. [Source](https://anneepolitique.swiss/de/projekte/inserateanalysen-und-daten/) · [Codebook](https://anneepolitique.swiss/wp-content/uploads/2026/06/Codebook-zum-Datensatz-der-Abstimmungsinserate_20260308.pdf) · [CSV](https://anneepolitique.swiss/wp-content/uploads/2026/05/Datensatz-der-Abstimmungsinserate_20260308.csv). La version est rétrospective, pas une preuve de disponibilité historique ; couverture des titres variable (annexe A1). Swissvotes indique déjà un total d'annonces agrégé, potentiellement calculé jusqu'au scrutin, donc ne pas le considérer ex ante. Le codebook identifie OFS et lien Swissvotes : vérifier l'identité via lien Swissvotes et date, jamais par numéro OFS supposé équivalent. Un rapport APS est annoncé à J−10, le cutoff fixe J−11 est conservateur. L'audit ne produit que des statistiques de couverture nationales, sans position des annonces, données individuelles, segmentation par territoire ou ciblage. Pas de contenu ni résultat cible chargé. Pas de valeurs postérieures à 2022 exportées ; absence de lignes ne prouve pas absence de publication. Hypothèse de faisabilité : couverture suffisante d'informations publiées avant J−11 et concordance avec rapports contemporains. Pas de benchmark ni admission avant vérification. Le téléchargement via navigateur a échoué (CSV non supporté) ; audit binaire transféré à Actions, résultat en attente.

## Backlog priorisé

1. V13.1 : audit de schéma, hash, couverture et jointure ; vérifier licence, comparer dates et versions aux rapports contemporains et déterminer la redondance avec les variables déjà présentes.
2. V13.2 : inventaire des archives historiques de sondages agrégés avant vote, en distinguant part attendue, intention et probabilité ; priorité aux 4 dates sans rapport média V10.2 et aux marges nationales sous-couvertes.
3. V13.3 : diagnostic des erreurs locales sur les sorties V11.3 ; comparer des modèles géographiques agrégés sans segmentation individuelle, puis validation chronologique imbriquée, uniquement si nouvelle hypothèse identifiable.
4. V12.2 : reprendre si nouvelle preuve d'édition historique. Ne pas répéter les téléchargements inchangés.

Toutes les mesures futures sur la population de référence, MAE macro par objet, centrée, nationale et cantonale ; poids ex ante pour prédiction, bulletins réels uniquement pour scoring. Bootstrap apparié par date, diagnostic par objet/pli/thème/canton/commune ; ajustement uniquement sur dates antérieures. Risque de surajustement aux mêmes 23 dates. Ne pas utiliser de résultats 2023+ ni promouvoir.

## Reprise V13.1 — alternative aux données CSV

[Incident HTTP 403 et audit des couvertures contemporaines](V13.1-report-fallback.md). Deux tests CSV réussis, aucune acquisition ; audit de rapports Swissvotes indépendant implémenté, aucun résultat nouveau. Le CSV reste manuel, ne pas relancer sans changement de source. V13.2 reste prioritaire si l'audit de couvertures échoue.

## Reprise du 25 novembre — V13.1 et V13.2

[Résultats de couverture APS](V13.1-cover-results.md) : 42/66 candidats datés, 14/23 dates, zéro admission ; acquisition intégrale différée. [Pilote V13.2](V13.2-source-pilot.md) : 8 candidats de sondages nationaux, six accords de dernière vague, deux premières vagues, aucun nouveau score. Priorité : compléter les vagues et vérifier provenance/licence ; V13.3 demeure en attente. Aucun benchmark répété.

## V13.2b — Trois vagues pour une même date

[Audit de provenance et couverture multi-vagues](V13.2b-multiwave.md) : 20 observations/12 objets/4 dates, 10/10 accords de dernière vague, 4 objets à trois vagues mais une seule date multi-vagues. CI précédente 3/3 réussie. Aucun score ni admission. Étendre à plusieurs dates anciennes avant benchmark ; sinon reprendre V13.3.

## V13.2c — Extension 2016–2018

[Acquisition et contrôle](V13.2c-historical-waves.md) : 33 observations, 12 objets multi-vagues sur 4 dates, 12/12 accords des dernières vagues. CI précédente 3/3 réussie. Zéro admission ; prochaine priorité : élargir les dates et certifier les versions, puis V13.3 si bloqué.

## V13.2d — Extension 2020

[Acquisition et contrôle](V13.2d-2020-waves.md) : 39 observations, 14 objets multi-vagues sur 5 dates, 14/14 accords des dernières vagues. CI précédente 3/3 réussie. Zéro admission ; provenance et couverture restent insuffisantes, reprendre V13.3 en parallèle.

## V13.3 — Diagnostic prioritaire

[Protocole](V13.3-protocol.md) : oracle L1 de translation constante sur prédictions V11.3/V8.1, comparaison de l'erreur résiduelle à 4 pp, bootstrap par date, diagnostic par domaine/fenêtre. Exécution à vérifier ; aucun fit ni nouveau score. V13.2 certification en attente, V13.1 admission différée. CI précédente 3/3 réussie.

## V13.3 — Résultats et réorientation

[Diagnostic terminé](V13.3-results.md) : V11.3 6,9558 pp, oracle de translation 5,2246 pp (IC [4,7902 ; 5,7036]), 55/66 objets restent au-dessus de 4 pp. Quatre tests ciblés et 3/3 jobs CI réussis. Aucun gain prédictif. Priorité 1 : V13.4, séparer amplitude des contrastes et structure géographique (oracle affine scoring-only, puis calibration chronologique seulement si justifiée). Priorité 2 : nouvelles informations historiques agrégées indépendantes ; priorité 3 : V13.2 certification des sources multi-vagues et V13.1/V12.2 uniquement sur nouvelle preuve. Pas de répétition des corrections cantonales V10.5/V10.6 sans hypothèse distincte.

## V13.4 — Amplitude contre structure

[Protocole préenregistré](V13.4-protocol.md) : diagnostic affine monotone scoring-only sur V8.1/V11.3, contrôle V13.3, cinq tests dont comparaison à un programme linéaire indépendant. Aucun coefficient exporté, aucun nouveau score prédictif. Benchmark à vérifier ; V13.2 toujours en attente de certification. CI précédente réussie (45670689207).

## V13.4 — Résultats et décision

[Résultats vérifiés](V13.4-results.md) : oracle affine V11.3 4,9266 pp (IC [4,5402 ; 5,3762]), gain d'amplitude de 0,2980 pp, 49/66 objets restent >4 pp. 5/5 tests ciblés, CI générale 3/3. V11.3 inchangée. Priorité V13.5 : diagnostic inter/intra-canton avec géographie vérifiée ; puis V14 sources agrégées indépendantes et audit de redondance. V11.5 extension historique déjà sans gain ; ne pas répéter. V13.2/1 et V12.2 restent conditionnées aux preuves de provenance. Pas de fit ni de promotion.

## V13.5 — Décomposition géographique

[Protocole préenregistré](V13.5-protocol.md) : oracle de translation cantonale et décomposition L2 exacte inter/intra sur les résidus historiques, jointure OFS contrôlée et reproduction des quatre métriques. Cinq tests implémentés ; CI précédente 3/3 réussie (45691590687). Aucun score nouveau ; priorité après diagnostic : V14 données indépendantes, puis certification V13.2. Aucun accès au holdout.


### Incident V13.5 — correction numérique

Le [premier benchmark](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45700042334) échoue avant chargement de l'artefact : le test des groupes inégaux exigeait une inégalité flottante stricte (28,93244816772078 contre 28,93244816772077 pp). [CI générale](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45700052778) : 683 tests réussis, 1 échec, 9 ignorés sur Ubuntu ; job municipal réussi. Correction du test avec tolérance absolue de 1e-8 pp, déjà appliquée à l'invariant du diagnostic. Aucun changement des métriques, du modèle, des données ou de la population. Le benchmark est relancé par le changement de test ; résultats réels non encore mesurés.

## V13.5 — clôture et suite V14

[Résultats vérifiés](V13.5-results.md) : oracle cantonal V11.3 3,7517 pp [3,5636 ; 3,9575], 18/66 objets >4 pp ; gain supplémentaire 1,4729 pp. 5 tests ciblés et 3/3 jobs CI réussis. Aucun gain prédictif. [Index et backlog V14](../v14_campaign/README.md) : audit de nouvelles sources institutionnelles agrégées, V13.2 encore en attente. Aucun test final.

## V13.2e — Extension 2021

[Acquisition et audit](V13.2e-2021-waves.md) : 45 observations, 16 objets, 6 dates multi-vagues, 16/16 accords dernière vague. CI du parent 3/3 réussie. Aucune admission ni nouveau score ; priorité aux dates indépendantes 2017–2019 et à la certification. V14.1 différée.

## V13.2f — Extension juin 2018

[Acquisition et audit](V13.2f-2018-june-waves.md) : 51 observations, 18 objets, 7 dates multi-vagues, 18/18 accords dernière vague, 51/51 publications à J−11 ou avant. CI du parent 3/3 réussie. Aucun nouveau score ni admission ; priorité aux dates 2017/2019 et à la certification.

## V13.2g — Extension février 2019

[Acquisition et audit](V13.2g-2019-february-waves.md) : 54 observations, 19 objets, 8 dates, 19/19 accords dernière vague ; CI du parent 3/3 réussie. Aucun nouveau score ni admission. Priorité : mai 2019/2017 puis certification ; ne pas prolonger l'inventaire sans preuve nouvelle.

## V13.2h — Extension mai 2019

[Acquisition et audit](V13.2h-2019-may-waves.md) : 60 observations, 21 objets, 9 dates, 21/21 accords dernière vague ; CI du parent 3/3 réussie. Divergence de terrain vague 1 documentée. Aucun nouveau score ni admission. Priorité à la certification ou piste indépendante, plutôt qu'à l'inventaire seul.

## V13.2i — Corroboration et droits

[Audit](V13.2i-corroboration.md) : 6/6 valeurs et dates de publication corroborées, deux conflits de terrain, zéro admission ; cinq contrôles négatifs réussis, CI parent 3/3. Inventaire gelé jusqu'à preuve nouvelle. Priorité V15.1 : audit de documents institutionnels historiques datés, distincts des brochures déjà testées. Aucun nouveau score.

## Suite V15.1a

[Registre V15](../v15_campaign/README.md) : 7 dossiers/3 dates, 34 entrées candidates, 15 familles provisoires, 6 contrôles négatifs, zéro admission. Priorité aux preuves primaires et à la couverture indépendante. CI parent 3/3. Meilleur V11.3 inchangé.

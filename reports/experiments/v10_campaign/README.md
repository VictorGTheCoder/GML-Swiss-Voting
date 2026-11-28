# Campagne V10 — journal de recherche

## Références

- V8.1 : MAE communale macro-objet **7,229527497606818** pp, référence gelée.
- V9 : meilleur score exploratoire 7,131910681945383 pp, gain non confirmé ; pas de promotion.
- Population de développement identique : 66 objets, 23 dates, 138 868 lignes, fenêtres 2016–2022. Objectif 4 pp.

Le [plan préenregistré](../../../experiments/municipal_v10/plan.json) détaille les dix versions par ordre de priorité. L'[état](../../../experiments/municipal_v10/state.json) constitue le checkpoint de reprise. Un premier pilote V10.1 a produit des scores exploratoires. Les travaux se font uniquement sur la branche expérimentale et les résultats sont évalués sur les mêmes fenêtres déjà explorées.

## Registre

| Version | Expérience | Statut | MAE communale | MAE cantonale | MAE nationale | Preuve |
|---|---|---|---:|---:|---:|---|
| V10.1 | Vote-expectation surveys | Terminé, gain non robuste (20 objets) | 7,2145 | 5,6634 | 3,8082 | [Extension](V10.1-extension.md) / [pilote](V10.1-pilot.md) |
| V10.2 | Campaign media coverage | Terminé, gain non robuste (54 objets) | 7,2271 | 5,6743 | 3,8250 | [Extension](V10.2-extension.md) / [pilote](V10.2-pilot.md) |
| V10.3 | Participation and ballot weights | Terminé, meilleur poids mais gain vote non robuste | 7,2169 | 5,7052 | 3,7757 | [Résultats](V10.3-results.md) |
| V10.4 | Aggregate poststratification and multilevel regression | Terminé, gain non robuste | 7,2039 | 5,6974 | 3,7757 | [Résultats](V10.4-results.md) |
| V10.5 | Independent canton forecasts / small area estimation | Terminé après deux incidents ; aucun gain communal (meilleure correction active) | 7,2441 | 5,7010 | 3,7710 | [Résultats](V10.5-results.md) |
| V10.6 | Hierarchical reconciliation (MinT) | Terminé, aucun gain communal (meilleur ajustement actif) | 7,2630 | 5,7157 | 3,7459 | [Résultats](V10.6-results.md) |
| V10.7 | Hybrid Gaussian-process profiles | Terminé, gain exploratoire non confirmé | 7,1315 | 5,6408 | 3,7757 | [Résultats](V10.7-results.md) |
| V10.8 | Official brochure corpus and semantic effects | Terminé, meilleur exploratoire non confirmé | 6,9886 | 5,5370 | 3,8465 | [Résultats](V10.8-results.md) |
| V10.9 | Socioeconomic data and object × commune interactions | Terminé, aucun gain fiscal | 7,2332 | 5,7064 | 3,7746 | [Résultats](V10.9-results.md) |
| V10.10 | Chronological ensemble | Terminé, pas de nouveau record | 7,1201 | 5,6053 | 3,8042 | [Résultats](V10.10-results.md) |

Les résultats oracles, les données historiquement non certifiées, les échecs et les intervalles descriptifs seront explicitement distingués des prévisions. Les résultats de 2023+ sont exclus de la modélisation. Aucune conclusion de succès prospectif ne sera tirée de ces seules dates réutilisées.

## Bilan du matin

[Rapport cumulatif du 24 novembre 2026](morning-report-20261124.md) : toutes les configurations mesurées, limites, incidents et prochaines étapes. V10.5 validée techniquement, sans gain ; V10.6–10.10 non évaluées dans le rapport initial.

## Reprise du 24 novembre

[Rapport cumulatif actualisé](followup-report-20261124.md) : 10/10 étapes mesurées ; meilleur exploratoire V10.8 à 6,9886. Aucun déploiement ni promotion. La tâche planifiée est désactivée.

## Campagnes suivantes
[V11](../v11_campaign/README.md) · [V12](../v12_campaign/README.md). V11.3 meilleur exploratoire 6,9558 pp ; V12.1 mesurée sans gain. Aucun modèle promu.

## Continuité de recherche

[V11](../v11_campaign/README.md) · [V12](../v12_campaign/README.md) · [V13](../v13_campaign/README.md) (index présent sur la branche V13). Meilleur exploratoire V11.3 6,9558 pp ; V12.4 sans gain. V12.2 différée, V13 audit de nouvelles sources. Aucun modèle promu.

## Diagnostic V13.3

[Résultats](../v13_campaign/V13.3-results.md) : oracle de translation V11.3 à 5,2246 pp, 55/66 objets restent au-dessus de 4 pp. Meilleur prédictif exploratoire 6,9558 pp inchangé ; priorité au diagnostic des contrastes, pas de promotion ni test final.

## Campagnes V14–V16

[V14](../v14_campaign/README.md) · [V15](../v15_campaign/README.md) · [V16](../v16_campaign/README.md). V15 identité binaire 3/3, données en quarantaine. V16.1 pilote d'incertitude par date mesuré ; meilleur prédictif V11.3 6,9558 pp inchangé. Aucun test final.

[V16.2 protocole](../v16_campaign/V16.2-protocol.md) : calibration du risque objet par bloc date, benchmark à vérifier, meilleur prédictif inchangé.

[V16.2 résultats](../v16_campaign/V16.2-results.md) : diagnostic exact de couverture du risque par objet, 12 configurations, 8 tests réussis ; aucun gain prédictif, V16.3 prioritaire.

## Campagnes V17–V18

[V17](../v17_campaign/README.md) : sources ElCom et STRU suspendues, aucune admission. [V18](../v18_campaign/README.md) : calibration d'amplitude mesurée sans gain ; meilleur exploratoire V11.3 6,9558 pp inchangé. Aucun test final.

[V18.2a](../v18_campaign/V18.2a-fedlex-protocol.md) : pilote des textes légaux originaux, 12 références/3 dates, 11 contrôles, aucun score ni admission. V11.3 reste meilleur exploratoire.

[V18.2a résultats et V18.2b](../v18_campaign/V18.2a-results-v182b-protocol.md) : acquisition de métadonnées 12/12, vérification PDF en attente. Aucun score nouveau, aucun test final.

- V18.2b : [audit PDF et correction r1](../v18_campaign/V18.2b-results-r1.md) ; 0/14 URL acceptée initialement, correctif de validation d'hôte documenté ; aucun score nouveau.

## Suites de recherche

[Index V11](../v11_campaign/README.md), [V18 et backlog courant](../v18_campaign/README.md). Les versions suivantes restent exploratoires et ne changent pas le modèle gelé.

[V18.3 résultats](../v18_campaign/V18.3-results.md) : aucun gain, meilleur exploratoire V11.3 inchangé. [V19](../v19_campaign/README.md) ouverte pour audit des jointures géographiques. Aucun test final.

[V19.1 résultats et V19.2](../v19_campaign/V19.1-results-v192-protocol.md) : non-équivalence des mutations OFS confirmée (6 lignes ajoutées), diagnostic de recouvrement des clés implémenté. Aucun gain mesuré.

[V19.2 résultats](../v19_campaign/V19.2-results.md) : diagnostic terminé, 12870/138868 lignes exposées numériquement, aucune admission. [V19.3a](../v19_campaign/V19.3a-deliberations-pilot.md) : pilote des délibérations par projet, aucune prédiction nouvelle. Meilleur V11.3 inchangé.

[V19.3a pilote structuré](../v19_campaign/V19.3a-structured-protocol.md) : trois affaires et quatre collections candidates ; aucun score nouveau ni admission.

[V19.3a résultats](../v19_campaign/V19.3a-structured-results.md) : 6 comptes, zéro admission. [V20](../v20_campaign/README.md) nouvelle expérience prédictive, score en attente. V11.3 inchangée.

[V20.1 résultats](../v20_campaign/V20.1-results.md) : aucun gain des trois intercepts historiques, CI 3/3 ; [V20.2](../v20_campaign/V20.2-protocol.md) transfert contextuel préspécifié, score à vérifier. V11.3 6,9558 pp inchangée.

[V20.2 résultats](../v20_campaign/V20.2-results.md) : aucun gain, 6,9816 pp ; clôture des résidus. [V21](../v21_campaign/README.md) contexte de session préspécifié, meilleur exploratoire inchangé.

[V21.1 résultats](../v21_campaign/V21.1-results.md) : aucun gain de contexte ; [V22](../v22_campaign/README.md) compression supervisée préspécifiée. Meilleur V11.3 inchangé.

[V22.1 résultats](../v22_campaign/V22.1-results.md) : aucun gain, supervision 7,4959 pp. [V23](../v23_campaign/README.md) audit de source indépendant préspécifié. Meilleur exploratoire V11.3 inchangé.

[V23.1 résultats et V23.2](../v23_campaign/README.md) : six cubes identifiés, schéma des deux cubes détaillés préspécifié, aucune admission ni nouveau score.

[V23.2–V23.3a](../v23_campaign/README.md) : schéma vérifié, 139 lignes, deux décisions historiques repérées, aucune admission. Source suspendue; V11.3 meilleur exploratoire inchangé.

[V24](../v24_campaign/README.md) : perte pseudo-Huber sur têtes standardisées, contrôle quadratique préspécifié. Score en attente, meilleur V11.3 inchangé.

[V24.1 résultats](../v24_campaign/V24.1-results.md) : nouveau minimum descriptif quadratique standardisée 6,950427808889042 pp, gain 0,005326 pp non robuste; pseudo-Huber négative. Aucun modèle promu, aucun test final. V25.1 audit de stabilité priorisé.

## Index des campagnes suivantes

- [V11](../v11_campaign/README.md)
- [V12](../v12_campaign/README.md)
- [V13](../v13_campaign/README.md)
- [V14](../v14_campaign/README.md)
- [V15](../v15_campaign/README.md)
- [V16](../v16_campaign/README.md)
- [V17](../v17_campaign/README.md)
- [V18](../v18_campaign/README.md)
- [V19](../v19_campaign/README.md)
- [V20](../v20_campaign/README.md)
- [V21](../v21_campaign/README.md)
- [V22](../v22_campaign/README.md)
- [V23](../v23_campaign/README.md)
- [V24](../v24_campaign/README.md)
- [V25](../v25_campaign/README.md)

Meilleur minimum descriptif V24.1 : 6,950427808889042 pp; V25.1a mesurée sans nouveau modèle, V25.1b en attente. Aucun test final.

[V25.1b clôturée](../v25_campaign/V25.1b-results.json) : stabilité descriptive positive sur 44/44 retraits, IC incluant zéro; [V26](../v26_campaign/README.md) audit de support thématique et source SECO candidate. Meilleur exploratoire inchangé, aucun test final.

[V26.1 résultats](../v26_campaign/V26.1-results.md) : audit 66 objets, 4 tests et CI 3/3; codes 4/5 expliquent 28.10 % de l'écart à 4 pp. V26.2 pilote SECO en quarantaine; meilleur V24.1 inchangé.

[V26.2b](../v26_campaign/README.md) : six millésimes cantonaux OPEN-BY identifiés, acquisition et couverture à vérifier; aucune donnée admise, aucun score nouveau.

[V26.2b résultats](../v26_campaign/V26.2b-results.json) : 6/6 fichiers acquis et empreintes vérifiées; couverture candidate 11/66 objets, 4/23 dates. V26.2c inspection des schémas préspécifiée, aucune admission, aucun nouveau score.

- V26.2c : [audit schéma et extension V26.2d](../v26_campaign/README.md#v262c-clôturée--v262d-extension-ciblée), 6/6 schémas vérifiés; trois millésimes supplémentaires en acquisition, aucune admission.

[V26.2d résultats](../v26_campaign/V26.2d-results.json) : 9 archives au total, 7/23 dates et 20/66 objets potentiellement couverts; V26.2e extraction stricte préspécifiée, aucune admission ni score nouveau.

[V26.2e résultats partiels](../v26_campaign/V26.2e-results.json) : 5/9 archives, 135 observations en quarantaine; quatre classeurs bloqués sur les deux Appenzell. Correctif r1 limité aux quatre échecs, résultat à vérifier. Aucun score nouveau ni admission.

[V26.2e r1 résultats cumulés](../v26_campaign/V26.2e-r1-results.json) : 9/9 archives, 243 observations en quarantaine, 7/23 dates. V26.2f : nouveau millésime et trois taux nationaux candidats, aucune admission. V24.1 inchangée.

[V26.2f audit de provenance](../v26_campaign/V26.2f-source-audit.json) : deuxième rupture de dénominateur identifiée en juillet 2016, deux PDF candidats non certifiés et acquisition ciblée d'août 2018 en cours. Aucun nouveau score ni admission.

[V26.2f clôturée](../v26_campaign/V26.2f-results.json) : 10 archives, 270 observations en quarantaine, 8/23 dates ; SECO suspendu. [V27](../v27_campaign/README.md) partage des partitions des têtes XGBoost préspécifié, aucun score nouveau ni test final.

[V27.1 clôturée](../v27_campaign/V27.1-results.json) : 7,263734 pp, +0,313306 vs V24.1. [V28](../v28_campaign/README.md) planifiée; meilleur inchangé.

[V28.1 inventaire](../v28_campaign/V28.1-source-inventory.json) : 20 objets attentes, 54 médias, 21 candidats Tamedia datés; nouvelle édition fög 2018 en quarantaine. Audit de scores figés implémenté, résultat à vérifier; aucun fit ni admission.

[V28.1 r1](../v28_campaign/README.md) : audit initial bloqué par le périmètre SRG mixte; couverture déclarée historique corrigée de 65 à 41/66, 48 lignes 2023+ exclues explicitement, 4 tests initiaux réussis. Correctif en vérification, meilleur exploratoire inchangé.

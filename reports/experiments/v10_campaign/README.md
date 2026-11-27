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

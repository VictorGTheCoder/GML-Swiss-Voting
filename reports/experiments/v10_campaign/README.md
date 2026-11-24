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
| V10.8 | Official brochure corpus and semantic effects | En attente | — | — | — | — |
| V10.9 | Socioeconomic data and object × commune interactions | En attente | — | — | — | — |
| V10.10 | Chronological ensemble | En attente | — | — | — | — |

Les résultats oracles, les données historiquement non certifiées, les échecs et les intervalles descriptifs seront explicitement distingués des prévisions. Les résultats de 2023+ sont exclus de la modélisation. Aucune conclusion de succès prospectif ne sera tirée de ces seules dates réutilisées.

## Bilan du matin

[Rapport cumulatif du 24 novembre 2026](morning-report-20261124.md) : toutes les configurations mesurées, limites, incidents et prochaines étapes. V10.5 validée techniquement, sans gain ; V10.6–10.10 non évaluées dans le rapport initial.

## Reprise du 24 novembre

[Rapport cumulatif actualisé](followup-report-20261124.md) : V10.6 terminée, V10.7–V10.10 à poursuivre.

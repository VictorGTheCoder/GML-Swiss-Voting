# Campagne V10 — rapport de reprise, 24 novembre 2026

**6/10 étapes mesurées.** Référence V8.1 7,2295 pp ; meilleur score exploratoire du projet V9 7,1319 pp, inchangé. Objectif 4 pp. Les 66 objets / 23 dates / 138 868 observations restent identiques. Les expériences sont comparées séparément à V8.1, sauf mention explicite. Pas de promotion.

[Rapport du matin — toutes les configurations V10.1 à V10.5](morning-report-20261124.md) · [Plan](../../../experiments/municipal_v10/plan.json) · [Journal](README.md)

| Version | Meilleure variante active (extension si disponible) | Commune | Canton | Suisse | Statut |
|---|---|---:|---:|---:|---|
| V8.1 | Référence | 7,2295 | 5,7037 | 3,7757 | Gelée |
| V9 | E5 document 16 | 7,1319 | — | — | Exploratoire |
| V10.1 | expectation25 | 7,2145 | 5,6634 | 3,8082 | Gain non robuste |
| V10.2 | tone_volume | 7,2271 | 5,6743 | 3,8250 | Gain non robuste |
| V10.3 | last_reanchor | 7,2169 | 5,7052 | 3,7757 | Gain non robuste |
| V10.4 | margin_ridge | 7,2039 | 5,6974 | 3,7757 | Gain non robuste |
| V10.5 | centered25 | 7,2441 | 5,7010 | 3,7710 | Dégradation |
| V10.6 | center_shrink25 | 7,2630 | 5,7157 | 3,7459 | Dégradation |
| V10.7 | Processus gaussiens | — | — | — | À faire |
| V10.8 | Corpus et effets | — | — | — | À faire |
| V10.9 | Économie détaillée | — | — | — | À faire |
| V10.10 | Ensemble | — | — | — | À faire |

## V10.6 — toutes les configurations

[Benchmark 45358533701](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45358533701) · [Artefact 14902549065](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45358533701/artifacts/14902549065) · 4 tests ciblés réussis.

| Variante | Commune | Centrée | Canton | Suisse | IC gain |
|---|---:|---:|---:|---:|---|
| reference | 7.2295 | 5.3701 | 5.7037 | 3.7757 | [0.0000, 0.0000] |
| pooled_control | 7.2295 | 5.3701 | 5.7090 | 3.7710 | [0.0000, 0.0000] |
| abs_diag | 7.4561 | 5.3945 | 6.0196 | 4.4476 | [-0.5936, 0.1311] |
| abs_shrink75 | 7.3595 | 5.4198 | 5.8321 | 4.0977 | [-0.4085, 0.1411] |
| abs_shrink25 | 7.3857 | 5.4474 | 5.8646 | 3.9903 | [-0.4451, 0.1101] |
| center_diag | 7.2855 | 5.4249 | 5.7266 | 3.7715 | [-0.1233, 0.0120] |
| center_shrink75 | 7.2681 | 5.4149 | 5.7137 | 3.7462 | [-0.1088, 0.0325] |
| center_shrink25 | 7.2630 | 5.4009 | 5.7157 | 3.7459 | [-0.1627, 0.0938] |
| abs_anchor75 | 7.2952 | 5.4354 | 5.7189 | 3.7710 | [-0.1664, 0.0204] |
| center_anchor75 | 7.2780 | 5.4157 | 5.7242 | 3.7710 | [-0.1129, 0.0164] |

## Analyse

- Aucune des huit réconciliations actives ne bat la référence communale 7,2295. Le meilleur ajustement est `center_shrink25`, 7,2630 (+0,0335 pp d'erreur). Son gain descriptif apparié [−0,1627 ; +0,0938] pp traverse zéro.
- `center_shrink25` réduit l'erreur nationale de 3,7757 à 3,7459 (poids propres) et 3,7398 (poids communs), mais dégrade l'erreur centrée de 5,3701 à 5,4009, et la MAE cantonale de 5,7037 à 5,7157 (poids propres), 5,7054 (poids communs).
- Les ajustements absolus sont moins performants. Cela concorde avec V10.5 : les prévisions cantonales absolues indépendantes atteignaient 9,1564 pp de MAE cantonale, contre 5,70896 pour le bottom-up et 5,9581 pour les contrastes directs recentrés. Une réconciliation ne crée pas à elle seule une source d'information supplémentaire.
- Le nombre d'erreurs hors-échantillon antérieures est faible vis-à-vis des 53 composantes du système. La régularisation est indispensable ; le benchmark ne constitue pas un test de toutes les formes de MinT. Les intervalles sont descriptifs et les dates déjà utilisées pour le développement.
- CI dédiée réussie. Le contrôle général initial a détecté C417 (map/lambda superflu), corrigé par une expression génératrice équivalente avec ce rapport ; résultat du nouveau contrôle à vérifier.

Décision : ne pas promouvoir. Réutiliser l'artefact de prédictions hors-échantillon dans une comparaison d'ensemble chronologique si pertinent, mais ne pas sélectionner les variantes en fonction de l'objet courant. Poursuivre à V10.7. Aucun déploiement, aucun résultat 2023+ dans la modélisation.


## Suite

V10.7 : modèle hybride avec noyaux structurés et profils historiques, en différenciant des essais V8 déjà réalisés. V10.8 : corpus avec validation des sections et effets. V10.9 : nouvelles données économiques réellement informatives et datées. V10.10 : combinaison exclusivement à partir de prédictions hors-échantillon et dates antérieures. Actualiser ce rapport après chaque expérience, y compris les blocages et les échecs. La reprise est programmée toutes les heures à partir de 10 h jusqu'à 17 h, heure suisse, sous réserve des capacités des exécutions. Les résultats ne seront pas extrapolés.

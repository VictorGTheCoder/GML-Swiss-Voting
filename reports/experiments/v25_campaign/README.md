# V25 — Stabilité descriptive des comparaisons

Suite [V24](../v24_campaign/README.md) et [V10](../v10_campaign/README.md). V8.1 gelée 7,229527497606818 pp; V9 7,131910681945383; minimum exploratoire V24.1 scaled_squared 6,950427808889042 pp. Aucun accès au test final.

## V25.1a — Retrait de fenêtres, mesuré

Calcul effectué à partir des moyennes par objet des trois fenêtres V24.1 et des effectifs 30/12/24, sans réentraînement. [Résultats exacts](V25.1a-results.json). La moyenne après retrait est pondérée par le nombre d'objets restants, non par le nombre de dates. Les sous-populations ne sont pas des scores comparables au benchmark complet.

| Fenêtre retirée | Objets | V8.1 | V11.3 | Quadratique standardisée | Huber | Gain vs V11.3 |
|---|---:|---:|---:|---:|---:|---:|
| 2016-2018 | 36 | 6.460404 | 6.441335 | 6.432617 | 6.508028 | 0.008719 |
| 2019-2020 | 54 | 7.247187 | 6.951461 | 6.950764 | 6.961918 | 0.000697 |
| 2021-2022 | 42 | 7.866071 | 7.402203 | 7.393834 | 7.508886 | 0.008370 |

La standardisation reste première parmi ces quatre variantes, mais le gain tombe sous 0,001 pp sans 2019–2020. Les résultats sont descriptifs : supprimer des dates de scoring ne supprime pas leur rôle dans l'entraînement historique ni dans la sélection des expériences. CI du parent [3/3 réussie](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/46067169689). Artefact V24.1 non expiré, identifiant et digest GitHub vérifiés; contenu non encore téléchargé dans ce passage.

## V25.1b — Audit par date préspécifié

Sur les métriques objet du même artefact (66 objets/23 dates), vérifier identité exacte des clés et scores de référence, refuser toute date hors 2016–2022. Retirer chaque date (23 cas), puis chaque bloc de trois dates consécutives (21 cas); calculer les quatre MAE et deux contrastes appariés, bootstrap descriptif par date (10 000 réplications, seed 25, ratio des sommes sur effectifs d'objets). Aucun ajustement ni sélection. Le fichier de résultats contient SHA-256 de l'entrée; le digest ZIP GitHub n'est pas recalculé. Deux tests synthétiques implémentés, exécution non confirmée. Le code ne lit que les métriques d'objets historiques agrégés, pas de résultats 2023+.

## Backlog priorisé

1. V25.1b : vérifier le run et consigner les contrastes directs, y compris négatifs; étendre à d'autres familles uniquement si les clés d'objet et provenance sont compatibles.
2. V26 : rechercher un apport ex ante indépendant pour les domaines codés 4/5 (>10 pp); ne pas rouvrir les sources suspendues sans preuve nouvelle. Prioriser certification ou historique élargi avec harmonisation, plutôt que petits réglages.
3. Validation finale uniquement après gel et autorisation distincte. Pas de promotion sur les dates réutilisées.

## V25.1b — Clôture mesurée (27 novembre 2026)

[Run](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/46074381004) et [artefact](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/46074381004/artifacts/15233508966), [résultats exacts](V25.1b-results.json) repris des logs. Tests 2/2, téléchargement source avec digest vérifié par Actions. Gain de standardisation positif dans 23/23 exclusions d'une date (0,001261 à 0,006550 pp) et 21/21 exclusions de trois dates consécutives (0,000867 à 0,006391 pp). Bootstrap date 10000 : gain standardisation [-0,001004 ; 0,016318], gain Huber vs standardisée [-0,212792 ; 0,060946]. Les deux intervalles incluent zéro; aucun nouveau fit, pas de validation indépendante ni correction pour sélection multiple. V25 clôturée. CI générale 1/3 (I001 dans le test, corrigé, nouvelle CI à vérifier); workflow audit manuel pour éviter répétition. [V26](../v26_campaign/README.md) ouverte.

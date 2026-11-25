# Recherche communale — V11 et suites

## Référence et périmètre
- [Campagne V10](../v10_campaign/followup-report-20261124.md), 10/10 étapes terminées, aucun modèle promu. V8.1 gelée 7,229527497606818 pp ; V9 exploratoire 7,131910681945383 ; V10.8 meilleur exploratoire 6,988599997055331. Population 66 objets, 23 dates, 138 868 observations (2016–22).
- Le benchmark externe [PR #87](https://github.com/VictorGTheCoder/GML-Swiss-Voting/pull/87) est séparé. Aucun score ni résultat 2023+ ne doit être utilisé comme cible, calibration ou sélection dans V11. Le test final reste réservé.
- Objectif scientifique 4 pp, pas un seuil de livraison. Données publiques agrégées, aucune inférence individuelle ni ciblage, aucune donnée du scrutin cible en entrée, aucune modification du modèle gelé.

## Registre
| Version | Hypothèse | État | Meilleure MAE |
|---|---|---|---:|
| V11.1 | Noyaux lexicaux intégraux et profil local complet | Terminé, aucun gain vs V10.8 | 7,0674 (nouveau candidat) |
| V11.2 | Audit exact des pages et mécanismes textuels | Terminé, aucun gain ; CI générale vérifiée | 7,1548 (nouveau candidat) | [Résultats](V11.2-results.md) |
| V11.3 | Délais et désaccord institutionnel | Terminé, gain exploratoire non confirmé | 6,9558 |
| V11.4 | Contrastes locaux, sélection imbriquée | Terminé, aucun gain; CI correction validée | 7,0199 (nouveau candidat) |

[Protocole V11.3](V11.3-protocol.md) · [Résultats](V11.3-results.md) · [Benchmark réussi](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45444093555). Nouveau meilleur exploratoire 6,9558 pp ; aucune promotion.

[Résultats V11.1](V11.1-results.md) · [Protocole V11.1](V11.1-protocol.md) · [Benchmark V11.1](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45409817577) · [Backlog et état](../../../experiments/municipal_v11/state.json).

## Backlog priorisé
1. V11.1 (terminé) : expérience factorielle noyaux et profil complet, analyse des erreurs par objet/thème/fenêtre/commune/canton.
2. V11.2 (terminé) : contrôle documentaire indépendant de la correspondance des pages, extraction de passages complets et représentation des mécanismes/direction du texte. Sources officielles et dates vérifiées ; aucun contenu post-vote.
3. V11.3 (terminé) : enrichir les signaux des objets par historiques parlementaires et analogues, sources datées ; contrôle redondances et ablations dans train.
4. V11.4 (terminé) : selon diagnostics de V11.1, comparaison de modèles de contrastes locaux avec sélection de rang et régularisation nested par dates, perte macro adaptée. Éviter la répétition des méthodes V6–V10.
5. V11.5 : audit d'extension historique (harmonisation communale, couverture et disponibilité ex ante), puis essai avec même évaluation.
6. V11.6 : robustesse rolling-origin et validation imbriquée avant tout choix de protocole final. Aucun test final sans autorisation distincte.

[Protocole V11.2](V11.2-protocol.md) : audit indépendant, question littérale, mécanismes contextuels et contrôles de couverture.

[Résultats V11.2](V11.2-results.md) · [Benchmark](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45420998869). V10.8 reproduite exactement ; audit plus strict réduit la couverture de 59 à 41 objets. Aucun gain confirmé.

## V11.4 — résultats

[Protocole](V11.4-protocol.md) · [Résultats](V11.4-results.md) · [Benchmark](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45486898263). Aucun gain : nested 7,3718 pp, mélange 7,0199. V11.3 reste meilleur exploratoire. V11.5 : audit historique, vérifier CI de la correction F401.

## V11.5 — historique

[Protocole](V11.5-protocol.md) : audit de la couverture 1960–1989, extension de la base géographique 1981–1989 et contrôle de demi-vie. Benchmark à vérifier. [CI V11.4 corrigée](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45496886074) réussie. Meilleur exploratoire inchangé.

### V11.5 — incident du benchmark (25 novembre 2026)

[Run 45506576707](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45506576707) : 3 tests ciblés réussis, les trois plis calculés et contrôles de replay/population franchis, puis `KeyError` à l’export : la variable `audit` documentaire était écrasée par l’audit historique dans la boucle. Artefact partiel [14971834596](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45506576707/artifacts/14971834596), aucun score validé avant manifeste complet. Correction : variables distinctes, export strict et test de régression, sans changer les configurations. Reproduction nécessaire. L’audit mesuré confirme 0/118 objets admissibles en 1960–1980 (couverture moyenne 79,62–79,66 %) et 55/56 en 1981–1989 (99,10–99,15 %). CI générale de la première tentative réussie. V11.3 demeure le meilleur exploratoire ; V11.6 reste prioritaire après résolution.

### V11.5 — clôture

[Résultats définitifs](V11.5-results.md) · [Reproduction réussie](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45514950645). 6,9678 pp avec extension à 1981 (5 ans), 7,0616 avec 15 ans sans extension et 7,0842 avec extension. Référence V11.3 reproduite exactement à 6,9558. Aucun gain.

### V11.6 — robustesse

[Protocole](V11.6-protocol.md) : refit local à 23 dates, deux variantes fixes, ancres nationales inchangées. Benchmark à vérifier. V12 : récupération des textes officiels manquants et contrôle apparié de couverture, puis descriptions multi-enjeux ; maintenir le registre et la séparation du test final.

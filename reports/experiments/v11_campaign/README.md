# Recherche communale — V11 et suites

## Référence et périmètre
- [Campagne V10](../v10_campaign/followup-report-20261124.md), 10/10 étapes terminées, aucun modèle promu. V8.1 gelée 7,229527497606818 pp ; V9 exploratoire 7,131910681945383 ; V10.8 meilleur exploratoire 6,988599997055331. Population 66 objets, 23 dates, 138 868 observations (2016–22).
- Le benchmark externe [PR #87](https://github.com/VictorGTheCoder/GML-Swiss-Voting/pull/87) est séparé. Aucun score ni résultat 2023+ ne doit être utilisé comme cible, calibration ou sélection dans V11. Le test final reste réservé.
- Objectif scientifique 4 pp, pas un seuil de livraison. Données publiques agrégées, aucune inférence individuelle ni ciblage, aucune donnée du scrutin cible en entrée, aucune modification du modèle gelé.

## Registre
| Version | Hypothèse | État | Meilleure MAE |
|---|---|---|---:|
| V11.1 | Noyaux lexicaux intégraux et profil local complet | Implémenté, benchmark à vérifier | — |

[Protocole V11.1](V11.1-protocol.md) · [Backlog et état](../../../experiments/municipal_v11/state.json).

## Backlog priorisé
1. V11.1 : expérience factorielle noyaux et profil complet, analyse des erreurs par objet/thème/fenêtre/commune/canton.
2. V11.2 : contrôle documentaire indépendant de la correspondance des pages, extraction de passages complets et représentation des mécanismes/direction du texte. Sources officielles et dates vérifiées ; aucun contenu post-vote.
3. V11.3 : enrichir les signaux des objets par historiques parlementaires et analogues, sources datées ; contrôle redondances et ablations dans train.
4. V11.4 : selon diagnostics de V11.1, comparaison de modèles de contrastes locaux avec sélection de rang et régularisation nested par dates, perte macro adaptée. Éviter la répétition des méthodes V6–V10.
5. V11.5 : audit d'extension historique (harmonisation communale, couverture et disponibilité ex ante), puis essai avec même évaluation.
6. V11.6 : robustesse rolling-origin et validation imbriquée avant tout choix de protocole final. Aucun test final sans autorisation distincte.

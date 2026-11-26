# V16 — Incertitude et robustesse (26 novembre 2026)

V10 10/10, V8.1 gelée 7,229527497606818 pp, V9 7,131910681945383 pp, V11.3 meilleur exploratoire 6,955753873756506 pp. Population historique inchangée (66 objets, 23 dates, 138868 lignes 2016–22). Aucun test final ni nouvelle prédiction. [V15](../v15_campaign/README.md) suspendue après 3 identités binaires confirmées mais droits et première publication non vérifiés.

## V16.1 — risque d'erreur par date, pilote mesuré

Hypothèse : une borne empirique actualisée sur les dates passées peut mieux décrire le risque d'erreur d'une session que la moyenne historique seule. Ce n'est pas une borne de l'erreur d'une commune ni une prédiction de résultat électoral. Prévisions V11.3 historiques déjà évaluées, moyennes macro-objet par date publiées dans V11.6 (arrondies à 0,0001 pp), aucun nouvel accès aux cibles. Neuf dates initiales, quatorze dates suivantes. Deux niveaux fixés 80 % et 90 %, quantile d'ordre ceil((n+1)*niveau), comparaison fenêtre initiale fixe et croissante. Toutes les bornes calculées exclusivement sur dates strictement antérieures. Pas de réglage de la couverture après observation. Les scores de date, et non les communes, sont les unités de calibration.

| Niveau | Calibration | Dates couvertes | Borne moyenne (pp) |
|---|---|---:|---:|
| 80% | fixed_initial_9 | 12/14 | 8.2687 |
| 80% | expanding | 12/14 | 8.3694 |
| 90% | fixed_initial_9 | 14/14 | 11.2261 |
| 90% | expanding | 14/14 | 10.4485 |

Les deux méthodes à 80 % manquent les mêmes deux dates (23.09.2018, 27.09.2020). À 90 %, la méthode croissante réduit la borne moyenne de 0,7776 pp sans perte de couverture observée ; sur 14 dates seulement, aucune preuve de gain prospectif ou garantie de couverture. Les dates ne sont pas supposées échangeables ; la formule de rang est inspirée de la calibration conformelle, mais aucune garantie conformelle n'est revendiquée. Risque de sélection du modèle V11.3 sur les dates réutilisées ; métrique macro-date distincte de la MAE macro-objet. Pas de modification du modèle ni de nouveau score prédictif. 6 contrôles réussis (population, causalité, fenêtre fixe, perturbation dernière cible, exclusion 2023+). Exécution avec les mêmes fonctions JS que le script versionné. [Résultats complets](V16.1-results.json). Reproduction : `node experiments/municipal_v16/date_risk.mjs`.

## Backlog priorisé

1. V16.2 : sur artefact V11.3 figé et haché, comparer bornes par date macro et par objet (maximum par bloc de date) avec métriques exactes, couverture, largeur et bootstrap par date ; pas de garantie prospective, pas de sélection selon les résultats. Préserver les 23 dates, distinguer warm-up/calibration et scoring, ne pas exporter de données individuelles.
2. V16.3 : rechercher une hypothèse prédictive indépendante sur données déjà admises, distincte des corrections et ensembles V10–V12 déjà testés. Préenregistrer l'ablation, vérifier la chronologie et la population, mesurer quatre métriques, gain apparié par date et diagnostics agrégés. En particulier vérifier la possibilité de refit national + local (V11.6 ne testait que local) avant tout run.
3. V13.2/V14/V15 : reprises uniquement sur nouvelle preuve de droits et disponibilité historique. Aucun entraînement avec données en quarantaine.

## V16.2 — implémentation et protocole

[Protocole](V16.2-protocol.md) : 12 configurations chronologiques sur l'artefact V11.3 immuable, contrôle de la MAE exacte et bootstrap par date. Benchmark à vérifier, aucun résultat nouveau. CI parent 3/3. V16.3 ensuite prioritaire pour la précision prédictive.

## V16.2 — clôture mesurée

[Résultats](V16.2-results.md) : 12 configurations, 42 objets sur 14 dates évaluées ; maximum par date 42/42 et 14/14, contrôle poolé aussi à 90% croissant avec une borne plus étroite. 8/8 tests ciblés ; deux erreurs de lint corrigées, CI nouvelle à vérifier. Pas de nouveau score prédictif. V16.3 priorité au refit niveau structural et local, contrôle V11.6.

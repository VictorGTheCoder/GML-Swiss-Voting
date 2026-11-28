# V27 — Partage des partitions dans la régression des profils (28.11.2026)

Suite [V26](../v26_campaign/README.md) et [V10](../v10_campaign/README.md). V8.1 gelée 7,229527497606818 pp ; V9 7,131910681945383 ; V24.1 minimum descriptif 6,950427808889042 pp. Population 66 objets, 23 dates, 138868 lignes, 2016–2022. Aucun test final.

## V27.1 — Protocole fixé avant score

Les six têtes de profils historiques de V24.1 sont entraînées séparément. Hypothèse : une partition commune des caractéristiques objet peut réduire la variance d'estimation lorsque plusieurs composantes dépendent d'une même structure, sans enrichissement des données. La [documentation XGBoost](https://xgboost.readthedocs.io/en/stable/tutorials/multioutput.html) décrit les feuilles vectorielles `multi_output_tree` avec `hist`, fonctionnalité expérimentale ; version CPU 3.4.1 déjà épinglée dans le dépôt. Aucun changement de l'environnement.

Deux configurations fixes : replay V24.1 quadratique standardisée, puis mêmes données, paramètres, cibles et standardisation mais feuilles vectorielles. Têtes constantes conservées à la moyenne historique ; si une seule tête varie, contrôle indépendant. Aucun choix de profondeur, de rang ou de régularisation sur les dates évaluées. Les partitions partagées ont une capacité différente ; un résultat négatif ne réfuterait pas toutes les approches multitâches. Comparaison principale contre le score et les prédictions épinglées V24.1 (contrôle numérique ligne à ligne 2e-6). V8.1 et V11.3 sont également conservées. Pipeline V24.1 repris sans modification du modèle gelé : préparation, texte, historiques, PCA, poids ex ante, ancre et hyperparamètres identiques ; aucune observation cible en entrée, aucune donnée 2023+. Toutes transformations apprises uniquement sur les fenêtres antérieures. Métriques par objet/pli/date/domaine/commune/canton, bootstrap apparié par date, empreintes et couverture comme V24.1. Aucun résultat oracle, aucune inférence individuelle ni ciblage. Les dates réutilisées ne constituent pas une validation indépendante.

Trois tests synthétiques implémentés (dimensions, invariance requêtes, équivariance affine, têtes constantes et rejet non-fini). Workflow dédié préspécifié. Aucun score ni test revendiqué avant exécution.

## Registre et backlog priorisé

1. V27.1 : vérifier benchmark, reproduction et CI ; enregistrer résultats et limites (fonctionnalité expérimentale).
2. Si pas de gain, ne pas multiplier les réglages ; rechercher un apport indépendant sur les objets ou une expérience à hypothèse distincte. SECO reste suspendu tant que les millésimes d'entraînement et métadonnées ne sont pas certifiés.
3. Validation finale uniquement après gel et autorisation distincte. Aucun modèle promu.

## V27.1 — Clôture mesurée, 28 novembre 2026

[Run réussi](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/46128815743), [artefact](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/46128815743/artifacts/15256732307), [CI générale](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/46128815711), [résultats exacts](V27.1-results.json). 3/3 tests et 3/3 jobs CI. 66 objets, 23 dates, 138868 lignes. Reproduction ligne à ligne V24.1 acceptée. Scores issus des logs; digest ZIP annoncé par GitHub, non recalculé. 14 fichiers exportés (métriques objet/pli/date/domaine/commune/canton, prédictions).

| Variante | Communale | Centrée | Nationale | Cantonale | Couverture (indicateur propre) |
|---|---:|---:|---:|---:|---:|
| reference | 7.229527 | 5.370059 | 3.775669 | 5.703708 | 59 |
| v113_institution | 6.955754 | 5.289917 | 3.781171 | 5.500339 | 59 |
| v241_scaled | 6.950428 | 5.289254 | 3.772388 | 5.493756 | 59 |
| scaled_replay | 6.950428 | 5.289254 | 3.772388 | 5.493756 | 66 |
| shared_splits | 7.263734 | 5.329630 | 3.920877 | 5.676038 | 66 |

Partage des partitions: +0,313306 pp vs V24.1; intervalle du gain apparié par date [-0,638726; -0,048601]. Plis 2016–18 / 2019–20 / 2021–22: 8,1566 / 7,4496 / 6,0548 vs 7,5718 / 6,9489 / 6,1745. Domaines 4 et 5 dégradés (11,8758 vs 10,1556; 10,3579 vs 10,0413). Toutes les métriques globales empirent. Ne pas sélectionner selon le pli a posteriori. Couvertures différentes selon indicateur, population de scoring identique. Résultat négatif pour cette configuration seulement, non pour toutes les approches multitâches. Dates réutilisées; aucune validation indépendante, aucun modèle promu. Aucune donnée admise. Le snapshot global de préparation est filtré par les contrôles du benchmark avant fit/calibration/scoring; aucune cible 2023+ utilisée. V24.1 reste minimum descriptif. V27 clôturée. [V28](../v28_campaign/README.md) audit indépendant des lacunes nationales priorisé.

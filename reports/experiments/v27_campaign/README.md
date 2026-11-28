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

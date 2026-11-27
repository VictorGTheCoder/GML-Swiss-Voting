# V24 — Objectif robuste des régressions de profils

Suite [V23](../v23_campaign/README.md), [V10](../v10_campaign/README.md). V10 10/10. V8.1 gelée 7,229527497606818 pp; V9 7,131910681945383; meilleur exploratoire V11.3 6,955753873756506 pp. Même population de développement 66 objets/23 dates/138868 lignes 2016–2022. Aucun test final.

## V24.1 — Protocole préspécifié

V13.5 attribue 39,1 % de la MSE au biais global, 28,0 % aux contrastes inter-canton et 32,9 % à l'intra-canton. Son oracle cantonal de 3,7517 pp utilise les résultats cibles, n'est pas prédictif. V20/V18 ont écarté les corrections résiduelles et d'amplitude simples; V11.4 teste ridge et rang, V22 compression supervisée. Hypothèse distincte : les six têtes XGBoost du profil historique sont actuellement ajustées en perte quadratique; les objets atypiques peuvent dominer la régression. Une perte pseudo-Huber (quadratique au voisinage de zéro, proche de L1 loin de zéro) pourrait réduire la MAE finale sans nouvelle variable. Source : [documentation XGBoost](https://xgboost.readthedocs.io/en/stable/parameter.html#learning-task-parameters).

Configurations fixées avant score: institution_replay (V11.3 inchangée), scaled_squared (centrage/écart-type historiques, base_score=0, perte quadratique), scaled_huber (mêmes transformations et paramètres, pseudo-Huber delta=1 sur échelle standardisée). La deuxième isole l'effet de l'échelle; comparaison principale scaled_huber contre scaled_squared puis V11.3. Aucune sélection de delta, aucun réglage opportuniste. Les têtes constantes restent à leur moyenne historique. Arbres, rang, corpus TF-IDF16, poids ex ante, variables institutionnelles et ancrage national inchangés; reste du pipeline V22.1/V11.3. La perte par tête n'est pas exactement la MAE communale et les paramètres fixes peuvent défavoriser un objectif. Les résultats des trois fenêtres restent exploratoires, provenance rétrospective des sources déjà admises.

Tests implémentés: dimensions/valeurs finies, invariance aux autres requêtes, tête constante, équivariance affine de la cible et rejet des entrées non finies/objectif inconnu. Replay exact des prédictions V11.3 (tolérance 2e-6), contrôle de la population, quatre MAE, bootstrap par date, diagnostics par objet/domaine/pli/canton/commune, manifeste et artefact de prédictions. Aucun résultat 2023+, pas de nouvel apport de données, aucune inférence individuelle ni ciblage. Workflow configuré; tests et score non encore vérifiés.

## Registre et backlog priorisé

1. V24.1 : vérifier benchmark et CI, enregistrer les résultats y compris négatifs et vérifier la comparaison principale; si échec ne pas multiplier les valeurs de delta.
2. V24.2 : si V24.1 est négative, prioriser la certification d'une source ex ante réellement indépendante ou un diagnostic de stabilité des choix sur dates réutilisées, sans rouvrir V19/V23 sans preuve nouvelle.
3. Avant toute promotion, protocole gelé et validation finale distincte autorisée. Aucune promesse d'atteindre 4 pp.

# V22 — Compression lexicale supervisée (27 novembre 2026)

Suite de [V21](../v21_campaign/README.md). V10 10/10 ; V8.1 7,229527497606818 gelée, V9 7,131910681945383, V11.3 meilleur exploratoire 6,955753873756506 pp. Les dates 2016–2022 ont été réutilisées, aucune validation prospective indépendante.

## V22.1 — Préspécification avant mesure

Hypothèse : la compression TF-IDF/SVD non supervisée privilégie la variance lexicale, pas les dimensions associées aux profils agrégés des objets. V11.1 a testé noyaux et profils complets, V12.3 multivues, pas cette ablation supervisée. Tester les mêmes têtes V11.3, PCA5, poids, sources, ancres et fenêtres, avec 1) replay TF-IDF16, 2) SVD6 non supervisé, 3) six axes de cross-covariance TF-IDF × six cibles historiques (niveau et 5 coefficients de profil), inspiré de [PLSSVD](https://scikit-learn.org/stable/modules/generated/sklearn.cross_decomposition.PLSSVD.html). Les cibles historiques sont standardisées et centrées ; TF-IDF identique, SVD de XᵀY, signes déterministes, directions nulles neutralisées. Pas d'ajustement sur les objets de validation, aucun accès aux cibles dans transform ; indicateur de couverture conservé. Ce n'est pas une nouvelle source ; risque de surajustement à 240–282 objets d'entraînement et provenance rétrospective inchangée. Le contrôle SVD6 isole la taille de la représentation. Le modèle aval est entraîné dans le même train (projection supervisée intégrée au modèle, pas de métaprédiction OOF revendiquée).

Trois fenêtres d'origine strictes, 66/23/138868, contrôles de replay exact, 2023+ interdit en apprentissage/évaluation, mêmes quatre MAE et bootstrap apparié par date, export par objet, domaine, pli, commune, canton. Aucun réglage après observation. Tests : forme et isolation des objets de validation, dates et chevauchement, covariance nulle. CI et benchmark à vérifier.

## Backlog priorisé

1. Mesurer V22.1 et comparer au replay et au contrôle de dimension ; aucun réglage supplémentaire sans gain informatif.
2. Chercher source indépendante ex ante avec provenance et licence explicites ; reprendre les sources en quarantaine seulement sur nouvelles preuves.
3. Vérifier robustesse sur développement et documenter le risque de réutilisation des dates, sans ouvrir le holdout. Aucun ciblage politique, aucune donnée individuelle, aucune promotion.

## Clôture mesurée

[Résultats V22.1](V22.1-results.md) : replay exact 6,9558 pp ; SVD6 7,0323 pp ; cross-cov6 7,4959 pp. Trois tests ciblés, CI 3/3. Aucun gain ni admission. [V23](../v23_campaign/README.md) prioritaire.

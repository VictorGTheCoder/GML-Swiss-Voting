# V4 — Thèmes unifiés et conséquences directes d'un « oui » (23 novembre 2026)

## Résultat

Le pipeline sémantique V4 est implémenté et testé, mais **la MAE n'a pas diminué**.
Sur les mêmes **66 objets / 23 dates de 2016–2022** et avec les paramètres
XGBoost/PCA5 de la campagne V3, la meilleure représentation reste celle
de V3: **9,0457 points de MAE structurelle**.

Les annotations V4 sont un **pilote documentaire**: **42 objets**, **45 effets
juridiques distincts**, **13 brochures du Conseil fédéral**. Les brochures,
pages, dates de bouclage, mécanismes, sens concret des quantités et éventuels
liens conditionnels figurent dans
[`data/annotations/yes_effects_v4.json`](../../../data/annotations/yes_effects_v4.json).
Toutes les annotations attendent une **relecture indépendante**.

## Représentation des thèmes

Swissvotes attribue jusqu'à trois branches de domaines `d1/d2/d3`, et chaque
branche comporte au maximum trois niveaux `e1/e2/e3`. Les codes sont des
étiquettes hiérarchiques, **pas des nombres**: `4 → 4.2 → 4.24`.

V4 calcule une seule liste **non ordonnée** de codes terminaux, par exemple
`4.24|6.2|6.12`. Les parents `4`, `4.2`, `6`, `6.1`
peuvent être ajoutés automatiquement, sans créer trois champs de position
ou répéter les parents plus d'une fois.

Les mécanismes d'un « oui » sont séparés des thèmes. Ainsi, les initiatives
de 2021 portant sur l'eau potable et sur les pesticides partagent des thèmes
mais ne décrivent pas la même intervention: restrictions d'éligibilité aux
paiements directs contre interdiction générale des pesticides synthétiques.

## Validation chronologique reproductible

[Exécution GitHub Actions ayant réussi](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45227193618)
— [fichiers de preuve, scores par objet/date et vocabulaires entraînés](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/45227193618/artifacts/14844670461).

| Variante | 2016–18 | 2019–20 | 2021–22 | MAE macro objets |
| --- | ---: | ---: | ---: | ---: |
| V3 domaines multi-hot | 9,0768 | 7,2305 | 9,9144 | **9,0457** |
| V4 thèmes précis « feuilles » | 9,1091 | 7,5198 | 10,1934 | 9,2144 |
| V4 feuilles + parents hiérarchiques | 9,0905 | 7,3496 | 10,0391 | 9,1189 |
| V3 domaines + effets sémantiques | 9,0768 | 7,3381 | 10,0759 | 9,1240 |
| V4 feuilles + effets sémantiques | 9,1091 | 7,6491 | 10,3004 | 9,2768 |

Les mêmes objets communaux sont évalués dans toutes les variantes. Le tableau
ne mesure pas l'apport des sondages V3 et **ne remplace pas** le candidat final
V2 ou la capture des prévisions du 29 novembre 2026.

Une amélioration conceptuelle n'est pas nécessairement une amélioration
prédictive. **Aucune nouvelle variante n'est promue.**

### Couverture utilisable pour l'entraînement

| Fenêtre évaluée | Annotations dans le train | Annotations dans les objets évalués |
| --- | ---: | ---: |
| 2016–2018 (train antérieur à 2016) | 0 sur 240 | 7 sur 30 |
| 2019–2020 (train antérieur à 2019) | 7 sur 270 | 9 sur 12 |
| 2021–2022 (train antérieur à 2021) | 16 sur 282 | 9 sur 24 |

Le train de la première fenêtre n'a **aucun exemple de mécanisme V4**,
et la majorité des dimensions sémantiques sont rares même pour le train
avant 2021. Dans ce premier train, on **n'ajoute aucune feature constante
de disponibilité**; sinon la simple présence d'une nouvelle colonne,
bien que non informative, peut perturber l'échantillonnage aléatoire de
colonnes de XGBoost. Cette correction a fait passer la dernière variante
de 9,3133 à **9,2768** et conserve le score V3 original.

Ces résultats n'établissent pas que les effets juridiques sont inutiles.
Ils démontrent qu'une **petite collection d'annotations récentes et très
spécifiques** ne permet pas encore d'apprendre un signal général
suffisant pour dépasser la référence.

## Contrôles de qualité

- Chaque annotation possède une clé d'objet/date exacte, une brochure
  officielle, une page imprimée et une paraphrase du changement direct.
- L'absence d'annotation ne devient jamais une absence d'effet : état
  `semantic_documented=0` et ensemble de tags inconnu.
- Les situations de maintien, hausse, retrait, restriction et conditionnalité
  portent sur une **quantité nommée**; elles ne codent pas un jugement moral
  ou un « pour/contre l'environnement » simpliste.
- Aucun résultat, score de votation, sondage post-scrutin ou résultat communal
  n'alimente la préparation des thèmes et des tags.
- Les vocabulaires multi-hot sont construits **uniquement sur les objets
  d'entraînement** de chaque fenêtre.
- La période 2023+ n'est pas chargée par le benchmark et la comparaison
  2023–2025 déjà exposée n'est pas réutilisée.
- **22 tests ciblés passent** dans le benchmark GitHub; la CI du dépôt
  contrôle également les tests sur Ubuntu et Windows.

Les dates imprimées `editorial_cutoff` sont des dates de **bouclage**, pas
une attestation que l'édition PDF actuellement accessible est identique à
l'édition publique avant chaque scrutin. Le statut reste
**`strict_forecast_ready=false`**.

## Suite prioritaire

Les **338 objets non annotés** et les **42 dossiers à relire** peuvent être
listés sans voir leurs résultats :

```bash
python -m scripts.modeling.semantic_review_queue_v4 \
  --output reports/generated/semantic_v4/review_queue.csv
```

La priorité est d'annoter les objets **antérieurs à 2016**, afin d'obtenir
un nombre suffisant d'exemples sémantiques dans les trois fenêtres, puis de
regrouper les instruments en familles génériques mieux observées.
Une deuxième relecture des pages des brochures doit précéder
l'adoption des étiquettes pour une prévision stricte.

Instructions: [`docs/project/semantic_v4.md`](../../../docs/project/semantic_v4.md).
